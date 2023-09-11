from collections import Counter
from dataclasses import dataclass
import re
import unicodedata

import httpx
import mwparserfromhell as mwp
import pypandoc
from wikipediaapi import Wikipedia

from goodwiki.constants import removed_sections, templates_to_keep, country_templates
from goodwiki.errors import CorruptWikitextError
from goodwiki.mwp_utils import (
    try_remove_obj,
    is_media_wikilink,
    RE_CLEAN_WIKILINK,
    RE_RM_MAGIC,
    is_category_wikilink,
    clean_wikilink,
    get_heading,
    try_replace_obj,
    parse_params,
    get_wikilink_text,
    get_template_name,
    is_parser_function,
)
from goodwiki.tags import TagTranscluder


@dataclass
class RawWikiPage:
    wikitext: str
    pageid: int
    revid: int


@dataclass
class PreprocessedWikitext:
    wikitext: str
    categories: list[str]
    unsupported_templates: Counter[str]
    description: str | None


@dataclass
class WikiPage:
    pageid: int
    title: str
    lang: str
    revid: int
    categories: list[str]
    description: str | None
    raw_wikitext: str
    wikitext: str
    markdown: str
    unsupported_tags: Counter[str]
    unsupported_templates: Counter[str]


WIKI_API_ROOT = "https://en.wikipedia.org/w/api.php"


class GoodwikiClient:
    markdown_list_double_space_regex = re.compile(r"^([0-9]+\.|-)(  +)", re.MULTILINE)
    markdown_empty_unordered_list_item_regex = re.compile(r"^-( *)$\n", re.MULTILINE)

    def __init__(self, user_agent: str = "goodwiki/1.0 (https://euirim.org)"):
        self.user_agent = user_agent

    def get_category_pages(self, category: str) -> list[str]:
        """
        Get articles in Wikipedia's main namespace belonging to the given category.

        Args:
            category: name of the Wikipedia category; include "Category:" prefix.

        Returns:
            list of page titles associated with given category.
        """
        wikiapi = Wikipedia(self.user_agent, "en")
        cat = wikiapi.page(category)
        # 0 namespace is normal articles on wikipedia (non-category, etc.)
        return [c.title for c in cat.categorymembers.values() if c.namespace == 0]

    async def get_page_from_wikitext(
        self, raw_wikitext: str, title: str, pageid: int, revid: int, with_styling: bool
    ):
        """
        Get WikiPage object from given wikitext.

        Args:
            raw_wikitext: unprocessed wikitext of page.
            title: title of page.
            pageid: page id of page.
            revid: revision id of page.
            with_styling: whether to include styling syntax in the markdown like bolding, italicizing.

        Returns:
            WikiPage object.
        """
        # Preprocess wikitext
        preprocessed = self.preprocess_wikitext(raw_wikitext)

        # Expand wikitext templates
        expanded_wikitext = await self.expand_templates(preprocessed.wikitext)

        # Postprocess to clean up html
        final_wikitext, unsupported_tags = self.postprocess_wikitext(
            expanded_wikitext, with_styling
        )

        # Convert to markdown
        markdown = self.wikitext_to_markdown(final_wikitext)

        return WikiPage(
            pageid=pageid,
            title=unicodedata.normalize("NFKC", title),
            lang="en",
            revid=revid,
            categories=sorted(preprocessed.categories),
            description=preprocessed.description,
            raw_wikitext=raw_wikitext,
            wikitext=final_wikitext,
            markdown=markdown,
            unsupported_tags=unsupported_tags,
            unsupported_templates=preprocessed.unsupported_templates,
        )

    async def get_page(self, title: str, with_styling: bool = False) -> WikiPage:
        """
        Download Wikipedia page with the given title. Parse it to get markdown
        and meta information like categories all packaged in a WikiPage
        object.

        Args:
            title: title of the Wikipedia page.
            with_styling: whether to include styling syntax in the markdown like bolding, italicizing.

        Returns:
            WikiPage object.

        Raises:
            CorruptWikitextError: if the downloaded wikitext is corrupt/invalid.
        """
        # Download raw page
        raw_page = await self.download_raw_page(title)

        return await self.get_page_from_wikitext(
            raw_page.wikitext,
            title=title,
            pageid=raw_page.pageid,
            revid=raw_page.revid,
            with_styling=with_styling,
        )

    async def download_raw_page(self, title: str) -> RawWikiPage:
        transport = httpx.AsyncHTTPTransport(retries=1)
        async with httpx.AsyncClient(transport=transport, timeout=30.0) as client:
            res = await client.post(
                f"{WIKI_API_ROOT}",
                data={
                    "action": "query",
                    "prop": "revisions",
                    "titles": title,
                    "rvslots": "main",
                    "rvprop": "ids|content",
                    "format": "json",
                },
                headers={
                    "User-Agent": self.user_agent,
                },
            )
        assert res.status_code == 200
        res = res.json()["query"]
        page = res["pages"][list(res["pages"].keys())[0]]
        pageid = page["pageid"]
        rev = page["revisions"][0]
        content = rev["slots"]["main"]["*"]
        revid = rev["revid"]
        return RawWikiPage(wikitext=content, pageid=pageid, revid=revid)

    def _handle_section_removal(self, section) -> None:
        cur_section = section
        while cur_section is not None:
            heading = get_heading(section)
            if heading in removed_sections:
                continue

    def preprocess_wikitext(self, wikitext: str) -> PreprocessedWikitext:
        """
        Preprocess wikitext in preparation for expanding templates, also
        extracting a list of categories in the process.

        Do minimal processing here as the wikitext structure may be abnormal
        as template transclusion may be required to form properly structured wikitext.

        As a result, parsing in this function may be unreliable (e.g. getting sections).
        """
        code = mwp.parse(wikitext, skip_style_tags=True)

        first_pass_sections = []
        categories = []
        for section in code.get_sections(
            flat=True, include_lead=True, include_headings=True
        ):
            # Remove comments
            for comment in section.ifilter_comments():
                try_remove_obj(comment, section)

            # Get category links and parse wikilinks
            for obj in section.filter_wikilinks(recursive=True)[::-1]:
                if is_media_wikilink(obj):
                    try_remove_obj(obj, section)
                elif is_category_wikilink(obj):
                    categories.append(
                        unicodedata.normalize(
                            "NFKC",
                            re.sub(RE_CLEAN_WIKILINK, "", str(obj.title)).strip(),
                        )
                    )
                    clean_wikilink(obj)
                else:
                    try_replace_obj(obj, get_wikilink_text(obj), section)

            # Apply magic code (!, table endings) and remove known big templates
            # This may seem redundant but should minimize postprocessing errors
            # after expanding templates (like corrupt wikitext/html, etc.)
            for temp in section.filter_templates(recursive=True)[::-1]:
                temp_name = get_template_name(temp)
                if temp_name == "!":
                    try_replace_obj(temp, "|", section)
                elif temp_name in {"end", "jctbtm"}:
                    try_replace_obj(temp, "|}", section)

            # Remove behavior switches (parser instructions)
            # See: https://en.wikipedia.org/wiki/Help:Magic_words
            first_pass_sections.append(re.sub(RE_RM_MAGIC, "", str(section)))

        first_pass_wikitext = "\n\n".join(first_pass_sections)
        code = mwp.parse(first_pass_wikitext)

        preprocessed_sections = []
        unsupported_templates = []
        short_description = None
        for section in code.get_sections(
            levels=[2], include_lead=True, include_headings=True
        ):
            # Most templates should be removed, since they are asides to the main
            # content. But some templates should be kept to preserve content
            # (like smallcaps, strike)
            for temp in section.filter_templates(recursive=True)[::-1]:
                temp_name = get_template_name(temp)
                if (
                    temp_name not in templates_to_keep
                    and temp_name not in country_templates
                    and not temp_name.startswith("lang-")
                    and not is_parser_function(temp_name)
                ):
                    try_remove_obj(temp, section)
                    if temp_name == "short description":
                        params = parse_params(temp)
                        short_description = unicodedata.normalize(
                            "NFKC", params.get("1", "").strip()
                        )
                        if short_description in ["none", ""]:
                            short_description = None
                    else:
                        unsupported_templates.append(temp_name)

            # Don't strip whitespace from ends of section due to it causing
            # issues with lists
            preprocessed_sections.append(str(section))

        return PreprocessedWikitext(
            wikitext="\n\n".join(preprocessed_sections),
            categories=categories,
            unsupported_templates=Counter(unsupported_templates),
            description=short_description.strip()
            if short_description is not None
            else None,
        )

    async def expand_templates(self, wikitext: str) -> str:
        transport = httpx.AsyncHTTPTransport(retries=1)
        async with httpx.AsyncClient(transport=transport, timeout=30.0) as client:
            res = await client.post(
                f"{WIKI_API_ROOT}",
                data={
                    "action": "expandtemplates",
                    "prop": "wikitext",
                    "text": wikitext,
                    "format": "json",
                },
                headers={
                    "User-Agent": self.user_agent,
                },
            )
        assert res.status_code == 200
        return res.json()["expandtemplates"]["wikitext"].strip()

    def postprocess_wikitext(
        self, wikitext: str, with_styling: bool
    ) -> tuple[str, Counter[str]]:
        """
        Postprocess wikitext after expanding templates in preparation for
        markdown conversion.
        """
        # need to skip style tags to avoid some rare section parsing errors
        code = mwp.parse(wikitext, skip_style_tags=True)

        # Remove undesirable sections (e.g. references)
        # Needs to be separate to handle subsections gracefully
        for section in code.get_sections(include_lead=True, include_headings=True)[
            ::-1
        ]:
            heading = get_heading(section)
            if heading in removed_sections:
                code.remove(section)
                continue

        # Reassemble to read style tags
        code = mwp.parse(str(code), skip_style_tags=False)

        sections = []
        unsupported_tags = []
        transcluder = TagTranscluder(with_styling)
        for section in code.get_sections(
            levels=[2], include_lead=True, include_headings=True
        ):
            # Remove comments
            for comment in section.ifilter_comments():
                try_remove_obj(comment, section)

            # Transclude tags
            for tag in section.filter_tags(recursive=True)[::-1]:
                trans_out = transcluder.transclude(tag, section)
                if trans_out.unknown:
                    unsupported_tags.append(trans_out.tag_name)

            # Remove wikilinks in favor of text; remove category links outright
            # if they don't have text. Remove media links outright
            for obj in section.filter_wikilinks(recursive=True)[::-1]:
                if is_media_wikilink(obj):
                    try_remove_obj(obj, section)
                elif is_category_wikilink(obj):
                    if obj.text is None:
                        try_remove_obj(obj, section)
                    else:
                        clean_wikilink(obj)
                else:
                    try_replace_obj(obj, get_wikilink_text(obj), section)

            # Remove external links
            for obj in section.filter_external_links(recursive=True)[::-1]:
                if obj.title is None or obj.title == "":
                    try_remove_obj(obj, section)
                    continue
                try_replace_obj(obj, obj.title, section)

            sections.append(str(section))

        # Be sure doc ends with newline
        return "\n\n".join(sections).strip() + "\n", Counter(unsupported_tags)

    def wikitext_to_markdown(self, wikitext: str) -> str:
        markdown = ""
        try:
            markdown = pypandoc.convert_text(
                wikitext,
                "gfm",
                format="mediawiki",
                extra_args=["--wrap=none"],
            )
        except RuntimeError as err:
            raise CorruptWikitextError from err

        # Normalize unicode using NFKC (removing characters like non-breaking spaces)
        markdown = unicodedata.normalize("NFKC", markdown)

        # Remove errant comments in markdown (empty spaces)
        markdown = re.sub(r"<!--.*?-->", "", markdown)
        # Sometimes tables leave weird artifacts
        markdown = re.sub(r"\\\|\}", "", markdown)
        # Remove lines with just spaces (should be after removing comments due
        # to some comments taking up full line)
        # TODO: This may cause code to be compressed
        markdown = re.sub(r"\n\s*\n", "\n\n", markdown)
        # Remove spaces before newline (trailing spaces)
        markdown = re.sub(r" *\n", "\n", markdown)
        # Remove double spaces in front of list items (pandoc problem)
        markdown = re.sub(self.markdown_list_double_space_regex, r"\1 ", markdown)
        # Remove empty unordered list items
        markdown = re.sub(self.markdown_empty_unordered_list_item_regex, "", markdown)
        # Avoid excessive escaping \[]
        # \$, \# continues to be escaped due to conflicts with math
        markdown = re.sub(r"\\(\[|\])", r"\1", markdown)

        # Remove errors/artifacts
        markdown = re.sub(
            r'Format price error: cannot parse value "(.*?)"', r"\1", markdown
        )
        markdown = markdown.replace("<sup>[update]</sup>", "")

        return markdown.strip()
