import asyncio
import json
import os

import click

from src.client import GoodwikiClient


def get_title_from_dirname(dirname: str) -> str:
    raise NotImplementedError


def slugify_title(title: str) -> str:
    return "_".join(title.strip().lower().split())


async def generate_e2e_snapshots(force: bool):
    cur_file_dir = os.path.dirname(os.path.realpath(__file__))
    e2e_dir = os.path.join(cur_file_dir, "./snapshots/e2e")

    e2e_pages = [
        "2009 NBA All-Star Game",
        "Azerbaijan",
        "Bengal famine of 1943",
        "Beryl May Dent",
        "Doctor Who (series 12)",
        "Elvis Presley",
        "Ender's Game",
        "Hannah Arendt",
        "Homs",
        "Lockheed Martin F-35 Lightning II",
        "Long and short scales",
        "Manhattan",
        "Oscar Wilde",
        "Pi",
        "Pomona College",
        "Richard Nixon",
        "Sirius",
        "Star Wars: Episode I – The Phantom Menace",
        "TRAPPIST-1",
        "Usain Bolt",
        "Widener Library",
    ]

    client = GoodwikiClient("goodwiki_test/1.0 (https://euirim.org)")

    for title in e2e_pages:
        page_dir = os.path.join(e2e_dir, slugify_title(title))
        if os.path.isdir(page_dir) and not force:
            continue
        os.makedirs(page_dir, exist_ok=False)

        page = await client.get_page(title)
        raw_file = os.path.join(page_dir, "raw.txt")
        wikitext_file = os.path.join(page_dir, "wikitext.txt")
        markdown_file = os.path.join(page_dir, "markdown.md")
        props_file = os.path.join(page_dir, "props.json")

        with open(raw_file, "w") as f:
            f.write(page.raw_wikitext)

        with open(wikitext_file, "w") as f:
            f.write(page.wikitext)

        with open(markdown_file, "w") as f:
            f.write(page.markdown)

        with open(props_file, "w") as f:
            json.dump(
                {
                    "title": page.title,
                    "lang": "en",
                    "pageid": page.pageid,
                    "revid": page.revid,
                    "categories": page.categories,
                    "description": page.description,
                    "unsupported_tags": page.unsupported_tags,
                    "unsupported_templates": page.unsupported_templates,
                },
                f,
                indent=2,
                sort_keys=True,
            )


@click.command()
@click.option(
    "-f",
    "--force",
    default=False,
    help="Force creating new snapshots even when they already exist.",
)
def main(force):
    asyncio.run(generate_e2e_snapshots(force))


if __name__ == "__main__":
    main()
