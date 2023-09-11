import re

from goodwiki.constants import parser_functions


# Filters for magic words that are parser instructions -- e.g., __NOTOC__
RE_RM_MAGIC = re.compile("__[A-Z]*__", flags=re.UNICODE)
# Filters for file/image links.
_media_prefixes = "|".join(["File", "Image", "Media"])
RE_RM_WIKILINK = re.compile(
    f"^(?:{_media_prefixes}):", flags=re.IGNORECASE | re.UNICODE
)
# Leave category links in-place but remove the category prefixes
_cat_prefixes = "|".join(["Category"])
RE_CLEAN_WIKILINK = re.compile(
    f"^(?:{_cat_prefixes}):", flags=re.IGNORECASE | re.UNICODE
)


def try_replace_obj(obj, replacement, section):
    try:
        section.replace(obj, replacement)
    except ValueError:
        # For unknown reasons, objects are sometimes not found.
        # (mwparserfromhell issue)
        pass


def replace_obj(obj, replacement, section):
    section.replace(obj, replacement)


def try_remove_obj(obj, section):
    try:
        section.remove(obj)
    except ValueError:
        # For unknown reasons, objects are sometimes not found.
        # (mwparserfromhell issue)
        pass


def remove_obj(obj, section):
    section.remove(obj)


def get_heading(section) -> str | None:
    """Get heading from section"""
    headings = section.filter_headings()
    if len(headings) == 0:
        return None
    return headings[0].title.strip().lower()


def is_media_wikilink(obj):
    return bool(RE_RM_WIKILINK.match(str(obj.title)))


def is_category_wikilink(obj):
    return bool(RE_CLEAN_WIKILINK.match(str(obj.title)))


def tags_to_delete(obj):
    return str(obj.tag).lower() in {"ref", "table"}


def get_wikilink_text(wikilink_obj):
    """
    Get text (wikicode object) from wikilink, returning either the title field
    if text does not exist or the text field otherwise.
    """
    if wikilink_obj.text is not None and wikilink_obj.text != "":
        return wikilink_obj.text
    return wikilink_obj.title


def clean_wikilink(obj):
    text = get_wikilink_text(obj)
    text = re.sub(RE_CLEAN_WIKILINK, "", str(text))
    obj.text = text


def parse_params(template_obj) -> dict[str, str]:
    # Param names should be stripped, unlike values.
    # This is possible: {{tempname| arg=test}}
    # Params with empty values are not added
    params = {
        p.name.strip(): str(p.value) for p in template_obj.params if str(p.value) != ""
    }
    return params


def get_template_name(template_obj) -> str:
    """
    Get template name from template object, standardizing the name
    by replacing underscores with spaces and lowercasing the first letter.

    This matches the guidelines of template names on Wikipedia, which are
    case-sensitive except the first letter and have spaces that are equivalent
    to underscores. See: https://meta.wikimedia.org/wiki/Help:Template#Case_sensitivity

    Also strip the spaces on either side of the template name, as that's what
    Wikipedia implicitly allows.
    """
    raw_name = str(template_obj.name)
    name = raw_name.replace(raw_name[0], raw_name[0].lower(), 1)
    return name.replace("_", " ").strip()


def is_parser_function(template_name: str) -> bool:
    if template_name != "" and template_name.split(":")[0] in parser_functions:
        return True
    return False
