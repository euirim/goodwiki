from dataclasses import dataclass

from goodwiki.mwp_utils import replace_obj, remove_obj


@dataclass
class TagTranscludeStatus:
    tag_name: str  # name of tag
    unknown: bool  # whether the tag was not recognized


class TagTranscluder:
    def __init__(self, with_styling: bool):
        self.with_styling = with_styling
        self.tags_to_keep = {
            "br",
            "sub",
            "sup",
            "blockquote",
            "math",
            "syntaxhighlight",
            "code",
            "pre",
            "ul",
            "li",
            "ol",
            "nowiki",
        }
        if with_styling:
            self.tags_to_keep.update(["u", "del"])

        self.tags_to_extract = {
            "p",
            "abbr",
            "bdi",
            "bdo",
            "cite",
            "data",
            "dfn",
            "mark",  # not used frequently enough to warrant preservation in output
            "ruby",
            "rp",
            "rt",
            "rb",
            "samp",
            "small",
            "time",
            "var",
            "center",
            "font",
            "a",
            "big",
            "onlyinclude",
            "section",
            "chem",
            "ce",
        }
        if not with_styling:
            self.tags_to_extract.update(
                [
                    "u",
                    "b",
                    "strong",
                    "i",
                    "em",
                    "del",
                    "s",
                    "strike",
                    "''",
                    "'''",
                    "'''''",
                ]
            )

        self.tags_to_delete = {
            "style",
            "hr",
            "wbr",
            "div",
            "table",
            "td",
            "tr",
            "th",
            "caption",
            "thead",
            "tfoot",
            "tbody",
            "noinclude",
            "hiero",
            "ref",
            "templatestyles",
            "phonos",
            "gallery",
            "indicator",
            "timeline",
            "references",
            "img",
        }

    def parse_attributes(self, raw_attr: list[str]) -> dict[str, str | None]:
        attributes = {}
        for a in raw_attr:
            a = a.strip()
            comps = a.split("=")
            prop = comps[0]
            val = None
            if len(comps) == 2:
                val = comps[1]
                if prop == "class":
                    val = val.strip()
            attributes[prop] = val
        return attributes

    def transclude(self, tag_obj, section) -> TagTranscludeStatus:
        tag_name = tag_obj.tag.strip().lower()
        tag_attrs = self.parse_attributes(tag_obj.attributes)
        unknown = False
        match tag_name:
            # Keep some tags as is
            case t if t in self.tags_to_keep:
                pass
            # Extract content from some tags
            case t if t in self.tags_to_extract:
                replace_obj(tag_obj, tag_obj.contents, section)
            # Delete some tags entirely, including content
            case t if t in self.tags_to_delete:
                remove_obj(tag_obj, section)
            # Rest of cases handle special tags (h1, b, i, em, ins, etc.)
            # if not handled already (like for no styling case)
            case "span":
                # flagicons have extra space that we need to remove
                if "flagicon" in tag_attrs:
                    remove_obj(tag_obj, section)
                else:
                    replace_obj(tag_obj, tag_obj.contents, section)
            case "h1" | "h2" | "h3" | "h4" | "h5" | "h6":
                # Replace with heading
                level = int(tag_name[1])
                equals_signs = "=" * level
                replace_obj(
                    tag_obj,
                    f"{equals_signs} {tag_obj.contents} {equals_signs}",
                    section,
                )
            case "b" | "strong":
                replace_obj(tag_obj, f"'''{tag_obj.contents}'''", section)
            case "i" | "em":
                replace_obj(tag_obj, f"''{tag_obj.contents}''", section)
            case "ins":
                # Replace with u
                replace_obj(tag_obj, f"<u>{tag_obj.contents}</u>", section)
            case "q":
                # Replace with text
                replace_obj(tag_obj, f'"{tag_obj.contents}"', section)
            case "s" | "strike":
                # Replace with del
                replace_obj(tag_obj, f"<del>{tag_obj.contents}</del>", section)
            case "kbd" | "samp" | "tt":
                # Replace with code
                replace_obj(tag_obj, f"<code>{tag_obj.contents}</code>", section)
            case "dl":
                # Replace with list
                replace_obj(tag_obj, tag_obj.contents, section)
            case "dt":
                replace_obj(tag_obj, f"; {tag_obj.contents}", section)
            case "dd":
                replace_obj(tag_obj, f": {tag_obj.contents}", section)
            case "poem":
                tag_obj.tag = "blockquote"
            case _:
                # If none of the previous cases match, remove outright
                remove_obj(tag_obj, section)
                unknown = True

        return TagTranscludeStatus(tag_name=tag_name, unknown=unknown)
