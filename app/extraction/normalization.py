"""Deterministic text normalization for extraction output."""

from __future__ import annotations

import re
import unicodedata

# Invisible / control characters to strip (preserve newlines for internal joins)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200d\ufeff]")
_SOFT_HYPHEN = "\u00ad"
# Line-break hyphenation: word-\ncontinuation
_DEHYPHENATE = re.compile(r"(\w)-\s*\n\s*(\w)", re.UNICODE)
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")
_MULTI_SPACES = re.compile(r"[^\S\n]+")


def normalize_unicode(text: str) -> str:
    """NFC normalization; remove zero-width and soft hyphens."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace(_SOFT_HYPHEN, "")
    text = _ZERO_WIDTH.sub("", text)
    text = _CONTROL_CHARS.sub("", text)
    return text


def dehyphenate(text: str) -> str:
    """Join words split across line breaks with trailing hyphens."""
    return _DEHYPHENATE.sub(r"\1\2", text)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces; trim lines; limit blank lines."""
    text = _MULTI_SPACES.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTI_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def normalize_block_text(text: str) -> str:
    """Full normalization pipeline for a single block."""
    text = normalize_unicode(text)
    text = dehyphenate(text)
    text = normalize_whitespace(text)
    return text


def normalize_for_comparison(text: str) -> str:
    """Normalization for header/footer fingerprinting (full-line match only)."""
    text = normalize_block_text(text)
    return re.sub(r"\s+", " ", text).strip().lower()
