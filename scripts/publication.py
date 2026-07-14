"""Boundaries between public article copy and internal pipeline notes."""

from __future__ import annotations

import re

MARKER = "<!-- === PIPELINE NOTES — NOT FOR PUBLICATION === -->"


def extract_public_copy(markdown_text: str) -> str:
    """Return publishable Markdown and reject ambiguous pipeline boundaries.

    Draft frontmatter and everything from the pipeline marker onward are internal
    metadata. Publishing refuses drafts without exactly one marker so internal
    notes cannot be sent accidentally.
    """
    if markdown_text.count(MARKER) != 1:
        raise ValueError("draft must contain exactly one pipeline notes marker")

    public_copy = markdown_text.split(MARKER, 1)[0]
    if public_copy.startswith("---"):
        frontmatter = re.match(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", public_copy, re.S)
        if not frontmatter:
            raise ValueError("draft has malformed YAML frontmatter")
        public_copy = public_copy[frontmatter.end():]

    public_copy = public_copy.strip()
    if not public_copy:
        raise ValueError("draft contains no public copy")
    return public_copy + "\n"
