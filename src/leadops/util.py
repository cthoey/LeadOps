from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse
import json
import re


def utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_iso() -> str:
    return date.today().isoformat()


def normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def domain_from_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def dedupe_key(kind: str, name: str, url: str | None) -> str:
    domain = domain_from_url(url)
    if domain:
        return f"{kind}:{domain}"
    return f"{kind}:{normalize_name(name)}"


def read_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    if not path.exists():
        return items
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
