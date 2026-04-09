from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import re


USER_AGENT = "leadops/0.1"


@dataclass(slots=True)
class ExtractedPage:
    final_url: str
    title: str
    meta_description: str
    text: str

    def lead_name(self) -> str:
        title = self.title.strip()
        if not title:
            host = urlparse(self.final_url).netloc
            return host or self.final_url
        return _clean_title(title)

    def raw_evidence(self, max_chars: int = 2400) -> str:
        parts: list[str] = []
        if self.title:
            parts.append(f"Title: {self.title}")
        if self.meta_description:
            parts.append(f"Description: {self.meta_description}")
        if self.text:
            snippet = self.text[:max_chars].strip()
            parts.append(f"Page text:\n{snippet}")
        return "\n\n".join(parts).strip()


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.meta_description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        tag_lower = tag.lower()
        if tag_lower == "title":
            self.in_title = True
        if tag_lower in {"script", "style", "noscript"}:
            self.skip_depth += 1
        if tag_lower == "meta":
            name = attr_map.get("name", "").lower()
            prop = attr_map.get("property", "").lower()
            if name == "description" or prop == "og:description":
                content = attr_map.get("content", "").strip()
                if content and not self.meta_description:
                    self.meta_description = content

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self.in_title = False
        if tag_lower in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_title:
            if data.strip():
                self.title_parts.append(data.strip())
            return
        text = _normalize_whitespace(data)
        if text:
            self.text_parts.append(text)


def fetch_and_extract(url: str, timeout_seconds: int = 20) -> ExtractedPage:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout_seconds) as response:
        body = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
    return extract_from_html(body, final_url=final_url)


def extract_from_html(html: str, *, final_url: str) -> ExtractedPage:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    parser.close()
    text = _normalize_whitespace(" ".join(parser.text_parts))
    return ExtractedPage(
        final_url=final_url,
        title=_normalize_whitespace(" ".join(parser.title_parts)),
        meta_description=_normalize_whitespace(parser.meta_description),
        text=text,
    )


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_title(title: str) -> str:
    for separator in (" | ", " - ", " — ", " · ", " / "):
        if separator in title:
            return title.split(separator, 1)[0].strip()
    return title.strip()
