import asyncio
import calendar
from collections import Counter
from dataclasses import dataclass
import datetime
import os
from typing import Generator

import click
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

from goodwiki.client import GoodwikiClient, WikiPage
from goodwiki.errors import CorruptWikitextError
from goodwiki.utils import get_batch, count_rows


PQ_SCHEMA = pa.schema(
    [
        ("pageid", pa.int64()),
        ("title", pa.string()),
        ("revid", pa.int64()),
        pa.field("description", pa.string(), nullable=True),
        ("categories", pa.list_(pa.string())),
        ("markdown", pa.string()),
    ]
)


@dataclass
class ChunkResult:
    results: list[dict]
    corrupt: list[str]
    failed: list[tuple[dict, Exception]]
    unsupported_tags: Counter[str]
    unsupported_templates: Counter[str]


def get_chunk(
    data_file: str, articles: list[dict] | None, chunk_size: int
) -> Generator[list[dict], None, None]:
    if articles is not None:
        for chunk_start in range(0, len(articles), chunk_size):
            chunk = articles[chunk_start : chunk_start + chunk_size]
            yield chunk
    else:
        for i, batch in enumerate(get_batch(data_file, chunk_size)):
            yield batch


def wikipage_to_arrow(page: WikiPage) -> dict:
    return {
        "title": page.title,
        "pageid": page.pageid,
        "revid": page.revid,
        "categories": page.categories,
        "description": page.description,
        "markdown": page.markdown,
    }


async def process_chunk(client: GoodwikiClient, chunk: list[dict]) -> ChunkResult:
    promises = [
        client.get_page_from_wikitext(
            item["wikitext"],
            item["title"],
            item["pageid"],
            item["revid"],
            with_styling=False,
        )
        for item in chunk
    ]
    p_results = await asyncio.gather(*promises, return_exceptions=True)
    results = []
    failed = []
    corrupt = []
    unsupported_tags = Counter()
    unsupported_templates = Counter()
    for i, p_res in enumerate(p_results):
        title = chunk[i]["title"]
        if isinstance(p_res, CorruptWikitextError):
            click.echo(f"- Corrupt wikitext (title={title})")
            corrupt.append(title)
            continue
        elif isinstance(p_res, WikiPage):
            results.append(wikipage_to_arrow(p_res))
            unsupported_tags.update(p_res.unsupported_tags)
            unsupported_templates.update(p_res.unsupported_templates)
            continue

        click.echo(f"- Failed to process {title}. Error: {p_res}")
        failed.append((chunk[i], p_res))

    return ChunkResult(
        results=results,
        corrupt=corrupt,
        failed=failed,
        unsupported_tags=unsupported_tags,
        unsupported_templates=unsupported_templates,
    )


@click.command()
@click.argument("data", type=click.Path(exists=True, dir_okay=False))
@click.argument("out", type=click.Path(exists=False, dir_okay=False, writable=True))
@click.option(
    "-b",
    "--chunk-size",
    default=50,
    help="Number of rows to read from source data file at once per process.",
)
def main(data, out, chunk_size):
    timestamp = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
    data_file = os.path.join(os.getcwd(), data)
    out_file = os.path.join(os.getcwd(), out)
    cur_file_dir = os.path.dirname(os.path.realpath(__file__))
    log_dir = os.path.join(cur_file_dir, f"../log/goodwiki/generate/{timestamp}")
    os.makedirs(log_dir, exist_ok=True)

    # num_cores = max(1, cast(int, os.cpu_count()) - 2)
    # click.echo(f"Starting {num_cores} processes to generate dataset.")

    click.echo("Analyzing source data...")
    num_chunks = sum([1 for _ in get_batch(data_file, chunk_size)])
    num_rows = count_rows(data_file, chunk_size)
    click.echo(f"{num_chunks} chunks detected with {num_rows} total rows.")

    click.echo("\nGenerating data...")
    failed_articles = []
    corrupt = []
    unsupported_tags = Counter()
    unsupported_templates = Counter()
    client = GoodwikiClient()
    with pq.ParquetWriter(
        out_file, schema=PQ_SCHEMA, version="2.4", compression="snappy"
    ) as writer:
        articles = None
        while True:
            with tqdm(total=num_chunks if articles is None else len(articles)) as pbar:
                for chunk in get_chunk(data_file, articles, chunk_size):
                    chunk_res = asyncio.run(process_chunk(client, chunk))

                    table = pa.Table.from_pylist(chunk_res.results, schema=PQ_SCHEMA)
                    writer.write(table)

                    failed_articles += chunk_res.failed
                    corrupt += chunk_res.corrupt
                    unsupported_tags.update(chunk_res.unsupported_tags)
                    unsupported_templates.update(chunk_res.unsupported_templates)
                    pbar.update(1)

            success_count = num_rows - len(failed_articles) - len(corrupt)
            click.echo(
                f" * {success_count}/{num_rows if articles is None else len(articles)} processed"
            )

            if len(failed_articles) == 0:
                break

            try_failures_again = input(
                f"\n{len(failed_articles)} pages failed to process. "
                + "Would you like to try them again? (yes/no)"
            )

            # The default case is try again to minimize user error
            if try_failures_again == "no":
                log_file = os.path.join(log_dir, "failures.txt")

                click.echo(f"Saving failed page titles to {log_file}...")
                with open(log_file, "w") as f:
                    for a in failed_articles:
                        f.write(f"{a[0]['title']} | {a[1]}\n")
                break

            # Get rid of error message
            articles = [fa[0] for fa in failed_articles]
            failed_articles = []

    result_row_count = count_rows(out_file, chunk_size)
    click.echo(f"Generated dataset with {result_row_count} rows.")

    unsupported_tag_file = os.path.join(log_dir, "unsupported_tags.csv")
    click.echo(f"Saving unsupported tags to {unsupported_tag_file}")
    pd.DataFrame(unsupported_tags.most_common(), columns=["tag", "count"]).to_csv(
        unsupported_tag_file,
        index=False,
    )

    unsupported_temp_file = os.path.join(log_dir, "unsupported_templates.csv")
    click.echo(f"Saving unsupported templates to {unsupported_temp_file}")
    pd.DataFrame(
        unsupported_templates.most_common(), columns=["template", "count"]
    ).to_csv(unsupported_temp_file, index=False)

    corrupt_file = os.path.join(log_dir, "corrupt.txt")
    click.echo(f"Saving corrupt pages to {corrupt_file}")
    with open(corrupt_file, "w") as f:
        for a in corrupt:
            f.write(f"{a}\n")


if __name__ == "__main__":
    main()
