"""Pure markdown-text helpers — extract_links/extract_tags/excerpt.

Rewritten as part of the Postgres migration to use plain string scanning
instead of the `re` module (the migration brief calls for avoiding regular
expressions entirely in the new code). Behavior is preserved exactly —
same inputs produce the same outputs as the old regex-based version — this
is a mechanical rewrite of *how* the parsing happens, not a change to
*what* counts as a tag or a link.

Run server-side on every note save to derive its tags/links; no DB
access, no request context — safe to reuse from any module without
pulling in a repository.
"""

_WORD_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_TAG_BODY_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-/")
_MD_STRIP_CHARS = set("`*_#>[]()~-")


def _find_first_of(content: str, chars: str, start: int) -> int:
    """Index of the first character in `content` (from `start` onward)
    that's a member of `chars`, or -1 if none of them appear again."""
    n = len(content)
    for idx in range(start, n):
        if content[idx] in chars:
            return idx
    return -1


def extract_links(content: str) -> list[str]:
    """Return unique, order-preserving list of wikilink titles referenced
    in content — `[[Note Title]]` or `[[Note Title|Display Text]]`.

    A faithful state-machine rewrite of the old
    `\\[\\[([^\\]|#]+)(?:\\|[^\\]]+)?\\]\\]` pattern: the title (group 1)
    stops at the first `]`, `|`, or `#`; a `#` there always fails the
    match (no path in the old pattern could consume it); a lone `]` (not
    doubled) also fails; only a genuine `|display]]` or a direct `]]`
    right after the title succeeds — same as the compiled regex, just
    spelled out as explicit scanning instead of backtracking.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    i = 0
    n = len(content)
    while i < n - 1:
        if content[i] != "[" or content[i + 1] != "[":
            i += 1
            continue

        stop = _find_first_of(content, "]|#", i + 2)
        if stop == -1:
            i += 1
            continue

        title = content[i + 2 : stop]
        stop_char = content[stop]

        if not title or stop_char == "#":
            i += 1  # empty title, or a '#' before any close — both are non-matches
            continue

        if stop_char == "]":
            if content[stop : stop + 2] == "]]":
                matched_end = stop + 2
            else:
                i += 1  # a lone ']' (not doubled) — non-match
                continue
        else:  # stop_char == "|" — optional "|display text" then "]]"
            close = _find_first_of(content, "]", stop + 1)
            if close == -1 or close == stop + 1 or content[close : close + 2] != "]]":
                # empty display text, no ']' at all, or it isn't doubled —
                # every one of those is a non-match for the old pattern too
                i += 1
                continue
            matched_end = close + 2

        stripped = title.strip()
        if stripped and stripped not in seen_set:
            seen_set.add(stripped)
            seen.append(stripped)
        i = matched_end
    return seen


def extract_tags(content: str) -> list[str]:
    """Return unique, order-preserving list of #tags referenced in content
    (letters, numbers, dashes, underscores, forward-slash for nested tags
    like #project/alpha).

    A '#' only starts a tag when it's not immediately preceded by a "word"
    character (letter/digit/underscore) — matching the old negative
    lookbehind `(?<!\\w)#(...)` exactly, e.g. "a#b" is not a tag but
    "(#b" or a '#' at the very start of the content is.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    n = len(content)
    i = 0
    while i < n:
        if content[i] == "#" and (i == 0 or content[i - 1] not in _WORD_CHARS):
            j = i + 1
            while j < n and content[j] in _TAG_BODY_CHARS:
                j += 1
            tag = content[i + 1 : j].strip()
            if tag and tag not in seen_set:
                seen_set.add(tag)
                seen.append(tag)
            i = j if j > i + 1 else i + 1
        else:
            i += 1
    return seen


def excerpt(content: str, length: int = 200) -> str:
    """Plain-text preview for a public note listing — strips the most
    common markdown punctuation and collapses whitespace/newlines so a
    card preview doesn't show raw '#', '*', or '[[' characters, then
    truncates on a word boundary.
    """
    stripped_chars = [(" " if ch in _MD_STRIP_CHARS else ch) for ch in content]
    # str.split() with no separator already splits on any run of
    # whitespace (spaces, tabs, newlines) and drops empty pieces — the
    # same normalization the old `\s+` collapse did, no regex needed.
    collapsed = " ".join("".join(stripped_chars).split())
    if len(collapsed) <= length:
        return collapsed
    return collapsed[:length].rsplit(" ", 1)[0] + "…"
