import asyncio
import json
import os

from tqdm import tqdm

from goodwiki.client import GoodwikiClient


FILE_DIR = os.path.dirname(os.path.realpath(__file__))
SNAPSHOT_DIR = os.path.join(FILE_DIR, "./snapshots/e2e")
TEST_USER_AGENT = "goodwiki_test/1.0 (https://euirim.org)"


def get_title_from_dirname(dirname: str) -> str:
    raise NotImplementedError


def slugify_title(title: str) -> str:
    return "_".join(title.strip().lower().split())


async def generate_e2e_snapshots(force: bool):
    cur_file_dir = os.path.dirname(os.path.realpath(__file__))
    e2e_dir = os.path.join(cur_file_dir, "./snapshots/e2e")

    e2e_pages = [
        "2009 NBA All-Star Game",
        "Adenanthos cuneatus",
        "Azerbaijan",
        "Bengal famine of 1943",
        "Beryl May Dent",
        "Binary search algorithm",
        "Byzantine civil war of 1341–1347",
        "Doctor Who (series 12)",
        "Elvis Presley",
        "Ender's Game",
        "Hannah Arendt",
        "Homs",
        "Lockheed Martin F-35 Lightning II",
        "Long and short scales",
        "Manhattan",
        "Meningitis",
        "Morpeth, Northumberland",
        "Nicotinamide adenine dinucleotide",
        "Oscar Wilde",
        "Pi",
        "Pomona College",
        "Portal (video game)",
        "Radiocarbon dating",
        "Richard Nixon",
        "Sirius",
        "Star Wars: Episode I – The Phantom Menace",
        "TRAPPIST-1",
        "Ulysses (poem)",
        "Usain Bolt",
        "USS Indiana (BB-1)",
        "Washington v. Texas",
        "Widener Library",
    ]

    client = GoodwikiClient(TEST_USER_AGENT)

    for title in tqdm(e2e_pages):
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


def pytest_generate_tests(metafunc):
    asyncio.run(generate_e2e_snapshots(False))

    snapshot_names = []
    for e in os.scandir(SNAPSHOT_DIR):
        if e.is_dir():
            snapshot_names.append(e.name)
    metafunc.parametrize("snapshot_name", snapshot_names)


def test_parse_snapshot(snapshot_name: str):
    snapshot_dir = os.path.join(SNAPSHOT_DIR, snapshot_name)
    raw_file = os.path.join(snapshot_dir, "raw.txt")
    wikitext_file = os.path.join(snapshot_dir, "wikitext.txt")
    markdown_file = os.path.join(snapshot_dir, "markdown.md")
    props_file = os.path.join(snapshot_dir, "props.json")

    with open(raw_file, "r") as f0, open(wikitext_file, "r") as f1, open(
        markdown_file, "r"
    ) as f2, open(props_file, "r") as f3:
        raw = f0.read()
        wikitext = f1.read()
        markdown = f2.read()
        exp_props = json.load(f3)

    client = GoodwikiClient(TEST_USER_AGENT)
    actual_page = asyncio.run(
        client.get_page_from_wikitext(
            raw,
            title=exp_props["title"],
            pageid=exp_props["pageid"],
            revid=exp_props["revid"],
            with_styling=False,
        )
    )

    assert actual_page.markdown == markdown

    actual_props = {
        "title": actual_page.title,
        "lang": actual_page.lang,
        "pageid": actual_page.pageid,
        "revid": actual_page.revid,
        "categories": actual_page.categories,
        "description": actual_page.description,
        "unsupported_tags": dict(actual_page.unsupported_tags),
        "unsupported_templates": dict(actual_page.unsupported_templates),
    }

    assert actual_props == exp_props
