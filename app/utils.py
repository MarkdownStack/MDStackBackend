import re

# [[Note Title]] or [[Note Title|Display Text]]
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")

# #tag  (letters, numbers, dashes, underscores, forward-slash for nested tags like #project/alpha)
TAG_RE = re.compile(r"(?<!\w)#([a-zA-Z0-9_\-/]+)")


def extract_links(content: str) -> list[str]:
    """Return unique, order-preserving list of wikilink titles referenced in content."""
    seen = []
    for match in WIKILINK_RE.finditer(content):
        title = match.group(1).strip()
        if title and title not in seen:
            seen.append(title)
    return seen


def extract_tags(content: str) -> list[str]:
    """Return unique, order-preserving list of #tags referenced in content."""
    seen = []
    for match in TAG_RE.finditer(content):
        tag = match.group(1).strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def normalize_folder_path(path: str) -> str:
    path = (path or "").strip().strip("/")
    # collapse duplicate slashes
    parts = [p for p in path.split("/") if p]
    return "/".join(parts)
