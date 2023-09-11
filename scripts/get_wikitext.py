import os

import click
import pyarrow.parquet as pq
from tqdm import tqdm


@click.command()
@click.option("-o", "--outfile", help="Title of article")
@click.argument("pqfile")
@click.argument("title")
def main(outfile, pqfile, title):
    pqfile = pq.ParquetFile(pqfile)
    title = title.strip()
    wikitext = None
    click.echo(f"Searching for: {title}")
    for batch in tqdm(pqfile.iter_batches(batch_size=1024)):
        for e in batch.to_pylist():
            if e["title"] == title.strip():
                wikitext = e["wikitext"]
                break

    if wikitext is None:
        click.echo(f"Article not found in {pqfile}")
        return

    if outfile is None:
        outfile = os.path.join(
            os.getcwd(), f"{'_'.join(title.strip().lower().split(' '))}.txt"
        )

    click.echo(f"Saving wikitext to: {outfile}")
    with open(outfile, "w") as f:
        f.write(wikitext)


if __name__ == "__main__":
    main()
