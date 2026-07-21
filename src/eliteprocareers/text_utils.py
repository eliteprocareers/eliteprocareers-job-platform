"""Shared text-cleaning helpers used across scoring and generation.

Extracted from generation/match_rationale.py (v13 session) so
scoring/embeddings.py can reuse the same HTML-stripping logic instead of
duplicating it. Behavior is unchanged for existing callers.
"""

import html
import re

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean_html_text(raw: str | None, max_chars: int | None = None) -> str:
    """Strips HTML tags/entities, collapses whitespace, and optionally caps
    length. ATS platforms (Greenhouse in particular) store descriptions as
    raw escaped HTML, not plain text -- passing that straight into an
    embedding or prompt wastes signal on markup that carries no meaning.

    max_chars=None means no truncation (caller decides if/how to cap).
    """
    if not raw:
        return ""
    text = html.unescape(raw)
    text = _HTML_TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "..."
    return text
