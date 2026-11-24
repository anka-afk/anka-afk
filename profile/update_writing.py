#!/usr/bin/env python3
"""Sync the latest posts from https://ankaanka.org/rss.xml into README.md."""

from __future__ import annotations

import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

RSS_URL = "https://ankaanka.org/rss.xml"
README_PATH = Path(__file__).resolve().parent.parent / "README.md"
START_MARKER = "<!-- RECENT_WRITING:START -->"
END_MARKER = "<!-- RECENT_WRITING:END -->"
MAX_ITEMS = 4


def fetch_rss_items(url: str = RSS_URL, limit: int = MAX_ITEMS) -> list[tuple[str, str, str]]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "anka-afk-profile-sync/1.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        xml_bytes = resp.read()

    root = ET.fromstring(xml_bytes)
    items: list[tuple[str, str, str]] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue

        # Convert "[推断智能 #03] Mamba..." into clean title + subtle suffix
        badge = ""
        m = re.match(r"^\[([^\]]+)\]\s*(.+)$", title)
        if m:
            badge = m.group(1).strip()
            title = m.group(2).strip()

        items.append((title, link, badge))
        if len(items) >= limit:
            break
    return items


def format_markdown(items: list[tuple[str, str, str]]) -> str:
    lines: list[str] = []
    for title, link, badge in items:
        safe_title = title.replace("[", "\\[").replace("]", "\\]")
        if badge:
            lines.append(f"- [{safe_title}]({link}) · *{badge}*")
        else:
            lines.append(f"- [{safe_title}]({link})")
    return "\n".join(lines)


def update_readme(readme_path: Path = README_PATH) -> bool:
    if not readme_path.exists():
        return False

    content = readme_path.read_text(encoding="utf-8")
    if START_MARKER not in content or END_MARKER not in content:
        return False

    try:
        items = fetch_rss_items()
    except Exception as exc:
        print(f"[update_writing] Skipped RSS fetch ({exc})", file=sys.stderr)
        return False

    if not items:
        return False

    block = f"{START_MARKER}\n{format_markdown(items)}\n{END_MARKER}"
    pattern = re.compile(
        re.escape(START_MARKER) + r"[\s\S]*?" + re.escape(END_MARKER),
        re.MULTILINE,
    )
    updated = pattern.sub(lambda _: block, content, count=1)

    if updated == content:
        print("[update_writing] No changes.")
        return False

    readme_path.write_text(updated, encoding="utf-8")
    print(f"[update_writing] Updated {len(items)} items in README.md.")
    return True


if __name__ == "__main__":
    update_readme()
