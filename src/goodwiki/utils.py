import os

from collections import Counter
import multiprocessing as mp
from typing import Generator, cast

import mwparserfromhell as mwp
import pyarrow.parquet as pq
from tqdm import tqdm

from goodwiki.constants import removed_sections, big_templates_to_remove


def get_batch(filename: str, batch_size: int) -> Generator[list[dict], None, None]:
    """
    Get batch of given batch size from given parquet file.
    """
    pqfile = pq.ParquetFile(filename)
    for batch in pqfile.iter_batches(batch_size=batch_size):
        yield cast(list[dict], batch.to_pylist())


def count_rows(pq_filename: str, batch_size: int) -> int:
    """
    Count rows of parquet file of given filename.
    """
    return sum([len(batch) for batch in get_batch(pq_filename, batch_size)])


def _streamline_wikitext(wikitext: str) -> str:
    """
    Remove references, external links, notes, infoboxes, refs, and tables
    from wikitext, since they're already excluded from final output.

    Need to do this to more accurately estimate tag and template counts
    in dataset, since we're removing these sections/components anyways.
    """
    code = mwp.parse(wikitext)
    sections = []
    for section in code.get_sections(
        flat=True, include_lead=True, include_headings=True
    ):
        # Get rid of certain sections
        headings = section.filter_headings()
        heading = None
        if len(headings) != 0:
            heading = headings[0].title.strip().lower()
        if heading in removed_sections:
            continue

        # Get rid of tables and refs
        for obj in section.ifilter_tags(recursive=True):
            name = obj.tag.strip().lower()
            if name in {"table", "ref"}:
                try:
                    section.remove(obj)
                except ValueError:
                    pass

        # get rid of infoboxes
        for obj in section.ifilter_templates(recursive=True):
            name = obj.name.strip().lower()
            for temp_rmv in big_templates_to_remove:
                if name.startswith(temp_rmv):
                    try:
                        section.remove(obj)
                    except ValueError:
                        pass

        sections.append(str(section))
    return "\n\n".join(sections)


def combine_dicts(a: dict[str, set], b: dict[str, set]) -> dict[str, set]:
    return dict(
        list(a.items()) + list(b.items()) + [(k, a[k] | b[k]) for k in set(b) & set(a)]
    )


def _count_templates_task(chunk: list[dict]) -> tuple[Counter, dict[str, set]]:
    res = Counter()
    temp_counts_by_article = {}
    for c in chunk:
        article_template_counter = Counter()
        code = mwp.parse(_streamline_wikitext(c["wikitext"]))
        for temp in code.ifilter_templates(recursive=True):
            name = temp.name.strip().lower()
            article_template_counter[name] += 1
        res += article_template_counter
        temp_counts_by_article[c["title"]] = article_template_counter
    return res, temp_counts_by_article


def count_templates(pq_filename: str) -> tuple[Counter, dict[str, set]]:
    """
    Count template names used in wiki articles in the given
    parquet file.
    """
    num_cores = max(1, cast(int, os.cpu_count()) - 2)
    chunk_size = 128
    num_chunks = sum([1 for _ in get_batch(pq_filename, chunk_size)])
    counts = Counter()
    temp_counts_by_article = {}
    with mp.Pool(num_cores) as pool:
        for chunk_res in tqdm(
            pool.imap(_count_templates_task, get_batch(pq_filename, chunk_size)),
            total=num_chunks,
        ):
            counts += chunk_res[0]
            temp_counts_by_article.update(chunk_res[1])
    return counts, temp_counts_by_article


def _count_tags_task(chunk: list[dict]) -> tuple[Counter, dict[str, set]]:
    res = Counter()
    tag_counts_by_article = {}
    for c in chunk:
        article_tag_counter = Counter()
        code = mwp.parse(_streamline_wikitext(c["wikitext"]))
        for temp in code.ifilter_tags(recursive=True):
            name = temp.tag.strip().lower()
            article_tag_counter[name] += 1
        res = article_tag_counter
        tag_counts_by_article[c["title"]] = article_tag_counter
    return res, tag_counts_by_article


def count_tags(pq_filename: str) -> tuple[Counter, dict[str, set]]:
    """
    Count tag names used in wiki articles in the given
    parquet file. Note that tags are not just HTML tags, they
    also include wikitext equivalents for them like list items.

    This code is repetitive but I was lazy.
    """
    num_cores = max(1, cast(int, os.cpu_count()) - 2)
    chunk_size = 128
    num_chunks = sum([1 for _ in get_batch(pq_filename, chunk_size)])
    counts = Counter()
    tag_counts_by_article = {}
    with mp.Pool(num_cores) as pool:
        for chunk_res in tqdm(
            pool.imap(_count_tags_task, get_batch(pq_filename, chunk_size)),
            total=num_chunks,
        ):
            counts += chunk_res[0]
            tag_counts_by_article.update(chunk_res[1])
    return counts, tag_counts_by_article
