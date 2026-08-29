"""Normalize email HTML for assessment and semantic indexing."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_QUOTE_MARKER = re.compile(
    r"^\s*(-{2,}\s*(?:original|forwarded) message\s*-{2,}|begin forwarded message:?\s*$|On .+ wrote:\s*$|From:\s.+|_{5,})",
    re.IGNORECASE | re.MULTILINE,
)
_SIGNATURE_DELIMITER = re.compile(r"^--\s*$", re.MULTILINE)
_MOBILE_SIGNATURE = re.compile(r"^\s*sent from my .*$", re.IGNORECASE | re.MULTILINE)


class _TextExtractor(HTMLParser):
    """Collect readable text while preserving useful block boundaries."""

    _BLOCK_TAGS = {"br", "div", "li", "p", "table", "td", "th", "tr"}
    _SKIP_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if normalized := " ".join(data.split()):
            self.parts.append(normalized)


def html_to_text(content_html: str) -> str:
    """Return readable text from an HTML email without quote/signature policy."""
    extractor = _TextExtractor()
    extractor.feed(content_html)
    extractor.close()
    text = " ".join(extractor.parts).replace("\r\n", "\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def current_message_text(content_html: str) -> str:
    """Return only the sender-authored portion of an email body."""
    body = html_to_text(content_html)
    if quoted_history := _QUOTE_MARKER.search(body):
        body = body[: quoted_history.start()]
    body = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith(">"))
    body = _SIGNATURE_DELIMITER.split(body, 1)[0]
    return _MOBILE_SIGNATURE.sub("", body).strip()
