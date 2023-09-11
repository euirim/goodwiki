import asyncio
import calendar
import datetime
import os

import click
import pyarrow as pa
from pyarrow import parquet
from tqdm import tqdm

from src.client import GoodwikiClient


PQ_SCHEMA = pa.schema(
    [
        ("pageid", pa.int64()),
        ("title", pa.string()),
        ("lang", pa.string()),
        ("revid", pa.int64()),
        ("articletype", pa.string()),
        ("wikitext", pa.string()),
    ]
)


def get_articles(client: GoodwikiClient) -> list[tuple[str, str]]:
    # if there are duplicates, featured articles supersede good articles when
    # labeling as the former is a greater signal of quality
    # See https://stackoverflow.com/questions/52429406/python-union-of-set-of-tuples
    categories = [("Category:Good_articles", "g"), ("Category:Featured_articles", "f")]
    acc = dict()
    for c in categories:
        articles = client.get_category_pages(c[0])
        cat_set = {(a, c[1]) for a in articles}
        acc.update(dict(cat_set))
    click.echo(f" * {len(acc)} articles found.")
    return list(acc.items())


async def download_article(
    client: GoodwikiClient, title: str, article_type: str
) -> dict:
    raw_article = await client.download_raw_page(title)
    # Expanding templates makes the parsing much more complicated
    # so I skip this. This means some information is lost, though
    # in practice it's not much.
    # expanded_article = await expand_templates(raw_article.wikitext)

    return {
        "lang": "en",
        "pageid": raw_article.pageid,
        "revid": raw_article.revid,
        "title": title,
        "articletype": article_type,
        "wikitext": raw_article.wikitext,
    }


async def download_articles(
    client: GoodwikiClient,
    titles: list[tuple[str, str]],
    pqwriter: parquet.ParquetWriter,
) -> list[tuple[str, str]]:
    # Don't use very large chunk size to follow API ettiquette
    chunk_size = 25

    failed_articles = []
    with tqdm(total=len(titles)) as pbar:
        for chunk_start in range(0, len(titles), chunk_size):
            chunk = [
                download_article(client, titles[i][0], titles[i][1])
                for i in range(chunk_start, min(chunk_start + chunk_size, len(titles)))
            ]

            raw_articles = await asyncio.gather(*chunk, return_exceptions=True)
            articles = []
            for i, article in enumerate(raw_articles):
                if not isinstance(article, dict):
                    failed_title = titles[chunk_start + i]
                    click.echo(
                        f"Failed to download {failed_title[0]}. Error: {article}"
                    )
                    failed_articles.append(failed_title)
                    continue
                articles.append(article)

            table = pa.Table.from_pylist(articles, schema=PQ_SCHEMA)
            pqwriter.write(table)

            pbar.update(len(chunk))

    return failed_articles


@click.command()
@click.argument("dest")
def main(dest: str) -> None:
    timestamp = calendar.timegm(datetime.datetime.utcnow().utctimetuple())
    cur_file_dir = os.path.dirname(os.path.realpath(__file__))
    dest_dir = os.path.join(
        os.getcwd(),
        dest,
        f"{timestamp}",
    )
    os.makedirs(dest_dir, exist_ok=True)

    wiki_client = GoodwikiClient()

    click.echo("Getting articles...")
    articles = get_articles(wiki_client)
    click.echo(f" * {len(articles)} unique articles found.")

    dest_file = os.path.join(dest_dir, "raw.parquet")

    with parquet.ParquetWriter(
        dest_file, schema=PQ_SCHEMA, version="2.4", compression="snappy"
    ) as writer:
        while True:
            click.echo(f"\nDownloading articles to {dest_file}...")
            failed_articles = asyncio.run(
                download_articles(wiki_client, articles, writer)
            )
            success_count = len(articles) - len(failed_articles)
            click.echo(f" * {success_count}/{len(articles)} downloaded")

            if len(failed_articles) == 0:
                break

            try_failures_again = input(
                f"\n{len(failed_articles)} articles failed to download. "
                + "Would you like to try them again? (yes/no)"
            )
            # The default case is try again to minimize user error
            if try_failures_again == "no":
                missing_log_dir = os.path.join(
                    cur_file_dir, "../log/goodwiki/missing_articles"
                )
                os.makedirs(missing_log_dir, exist_ok=True)
                log_file = os.path.join(missing_log_dir, f"{timestamp}.txt")

                click.echo(f"Saving failed article titles to {log_file}...")
                with open(log_file, "w") as f:
                    for a in failed_articles:
                        f.write(f"{a[1]} {a[0]}\n")

                break

            articles = failed_articles


if __name__ == "__main__":
    main()
