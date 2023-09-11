# GoodWiki

GoodWiki is a Python package that carefully converts Wikipedia pages into GitHub-flavored Markdown. Converted pages preserve layout features like lists, code blocks, math, and block quotes.

This package is used to generate the [GoodWiki Dataset](https://github.com/euirim/goodwiki).

## Installation

This package supports Python 3.11+.

1. Install via pip.

```bash
pip install goodwiki
```

2. Install pandoc. Follow instructions [here](https://pandoc.org/installing.html).

## Usage

### Initializing Client

```python
import asyncio
from goodwiki import GoodwikiClient

client = GoodwikiClient()
```

You can also optionally provide your own user agent (default is `goodwiki/1.0 (https://euirim.org)`):

```python

client = GoodwikiClient("goodwiki/1.0 (bob@gmail.com)")
```

### Getting Single Page

```python
page = asyncio.run(client.get_page("Usain Bolt"))
```

You can also optionally include styling syntax like bolding to the final markdown:

```python
page = asyncio.run(client.get_page("Usain Bolt", with_styling=True))
```

You can access the resulting data via properties. For example:

```python
print(page.markdown)
```

### Getting Category Pages

To get a list of page titles associated with a Wikipedia category, run the following:

```python
client.get_category_pages("Category:Good_articles")
```

### Converting Existing Raw Wikitext

If you've already downloaded raw wikitext from Wikipedia, you can convert it to Markdown by running:

```python
client.get_page_from_wikitext(
	raw_wikitext="RAW_WIKITEXT",
	# The rest of the fields are meant for populating the final WikiPage object
	title="Usain Bolt",
	pageid=123,
	revid=123,
)
```

## Methodology

Full details are available in this package's [GitHub repo README](https://github.com/euirim/goodwiki).

## External Links

* [GitHub](https://github.com/euirim/goodwiki)
* [Dataset](https://huggingface.co/datasets/euirim/goodwiki)
