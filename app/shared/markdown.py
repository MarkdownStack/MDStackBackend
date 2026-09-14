"""Pure markdown-text helpers — moved from app/utils.py.

Run server-side on every note save to derive its tags/links; no DB access,
no request context — safe to reuse from any module without pulling in a
repository.
"""

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


_MD_STRIP_RE = re.compile(r"[`*_#>\[\]()~-]")
_WS_RE = re.compile(r"\s+")


def excerpt(content: str, length: int = 200) -> str:
    """Plain-text preview for a public note listing — strips the most common
    markdown punctuation and collapses whitespace/newlines so a card preview
    doesn't show raw '#', '*', or '[[' characters, then truncates."""
    stripped = _WS_RE.sub(" ", _MD_STRIP_RE.sub(" ", content)).strip()
    if len(stripped) <= length:
        return stripped
    return stripped[:length].rsplit(" ", 1)[0] + "…"
