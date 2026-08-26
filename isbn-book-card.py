"""
Obsidian Python Bridge Script: ISBN -> Book Card (API mashup POC)

Select an ISBN (10 or 13 digits, hyphens tolerated), run the script and get a
full book card inserted in place of the selection:

- checksum **validation implemented by hand** (the classic weighted-sum
  algorithms — pure Python elegance),
- metadata fetched from **OpenLibrary**, gaps filled from **Google Books**
  (two public APIs mashed together, zero API keys),
- markdown card with YAML block, authors, publisher and cover image.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x + requests.
"""

import os
import re
import sys
from typing import Any

import requests

# --- Library Import ---
try:
    from ObsidianPluginDevPythonToJS import (
        ObsidianCommError,
        ObsidianPluginDevPythonToJS,
        _handle_cli_args,
        define_settings,
    )
except ImportError:
    print("ERROR: ObsidianPluginDevPythonToJS.py library not found.", file=sys.stderr)
    sys.exit(1)

try:
    from ObsidianPluginDevPythonToJS import is_handling_event
except ImportError:

    def is_handling_event() -> bool:  # type: ignore[misc]
        return bool(os.environ.get("OBSIDIAN_EVENT_NAME"))


if is_handling_event():
    sys.exit(0)

MY_SCRIPT_SETTINGS: list = []
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()

OPENLIBRARY_URL = "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
GOOGLEBOOKS_URL = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
HTTP_TIMEOUT = 8


# --- Pure core ---


def normalise_isbn(raw: str) -> str:
    """Strip hyphens/spaces; uppercase x for ISBN-10 tails."""
    return re.sub(r"[\s-]", "", raw).upper()


def is_valid_isbn(digits: str) -> bool:
    """Hand-rolled checksum validation for both ISBN generations."""
    if re.fullmatch(r"\d{9}[\dX]", digits):
        total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
        return total % 11 == 0
    if re.fullmatch(r"\d{13}", digits):
        total = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(digits))
        return total % 10 == 0
    return False


def _first(value: Any, *keys: str) -> str | None:
    """Dig the first non-empty value along a key path of dicts/lists."""
    current = value
    for key in keys:
        if isinstance(current, list):
            current = current[0] if current else None
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
        if current in (None, "", []):
            return None
    return str(current)


def parse_openlibrary(payload: dict[str, Any], isbn: str) -> dict[str, Any]:
    """Extract a card dict from OpenLibrary's jscmd=data payload."""
    entry = payload.get(f"ISBN:{isbn}") or {}
    return {
        "title": entry.get("title") or "",
        "authors": [a.get("name", "") for a in entry.get("authors", [])],
        "date": entry.get("publish_date") or "",
        "publisher": _first(entry, "publishers", "name"),
        "cover": (entry.get("cover") or {}).get("large")
        or (entry.get("cover") or {}).get("medium")
        or "",
        "url": entry.get("url") or "",
    }


def parse_googlebooks(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract filler fields from Google Books' volume list payload."""
    items = payload.get("items") or [{}]
    info = items[0].get("volumeInfo", {}) if items else {}
    cover = (info.get("imageLinks") or {}).get("thumbnail", "")
    return {
        "title": info.get("title", ""),
        "authors": info.get("authors", []),
        "date": info.get("publishedDate", ""),
        "publisher": info.get("publisher", ""),
        "cover": cover.replace("http://", "https://"),
    }


def merge_cards(primary: dict[str, Any], filler: dict[str, Any]) -> dict[str, Any]:
    """Fill empty primary fields with filler ones."""
    merged = dict(primary)
    for key, value in filler.items():
        if not merged.get(key) and value:
            merged[key] = value
    return merged


def render_card(isbn: str, card: dict[str, Any]) -> str:
    """Markdown card with a small YAML header."""
    authors = ", ".join(a for a in card["authors"] if a) or "Unknown author"
    lines = [
        "---",
        f'title: "{card["title"] or isbn}"',
        f"author: [{authors}]",
        f"isbn: '{isbn}'",
        "---",
        "",
        f"# {card['title'] or isbn}",
        "",
        f"**Author(s):** {authors}",
    ]
    pub_bits = " · ".join(b for b in (card["date"], card["publisher"]) if b)
    if pub_bits:
        lines.append(f"**Published:** {pub_bits}")
    if card["cover"]:
        lines += ["", f"![cover]({card['cover']})"]
    if card["url"]:
        lines += ["", f"[OpenLibrary page]({card['url']})"]
    lines.append("")
    return "\n".join(lines)


# --- Network helpers ---


def fetch_card(isbn: str) -> dict[str, Any]:
    """Query both sources; network errors degrade to whatever we already have."""
    ol_payload: dict[str, Any] = {}
    gb_payload: dict[str, Any] = {}
    try:
        resp = requests.get(OPENLIBRARY_URL.format(isbn=isbn), timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            ol_payload = resp.json()
    except requests.RequestException as e:
        print(f"WARNING: OpenLibrary unreachable: {e}", file=sys.stderr)
    try:
        resp = requests.get(GOOGLEBOOKS_URL.format(isbn=isbn), timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            gb_payload = resp.json()
    except requests.RequestException as e:
        print(f"WARNING: Google Books unreachable: {e}", file=sys.stderr)

    return merge_cards(parse_openlibrary(ol_payload, isbn), parse_googlebooks(gb_payload))


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    raw = obsidian.get_selected_text()
    isbn = normalise_isbn(raw or "")

    if not isbn:
        obsidian.show_notification("Select an ISBN first.", 4000)
        return
    if not is_valid_isbn(isbn):
        obsidian.show_notification(f"'{isbn}' fails the ISBN checksum.", 5000)
        return

    card = fetch_card(isbn)
    if not any((card["title"], card["authors"], card["cover"])):
        obsidian.show_notification(f"No metadata found for {isbn}.", 5000)
        return

    obsidian.replace_selected_text(render_card(isbn, card))
    obsidian.show_notification(f"Book card created: {card['title']}", 4000)


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
