"""
Obsidian Python Bridge Script: PDF -> Markdown Note (optional-dep showcase)

Finds PDF links in the active note (``[[doc.pdf]]`` or ``[doc](doc.pdf)``),
extracts their text with **pypdf** and creates a sibling markdown note:

    Doc.pdf  →  Doc (Extracted).md

with one section per page plus a light heading heuristic (short ALL-CAPS
lines become `##` headings).

`pypdf` is OPTIONAL: without it you get a clean install hint, never a crash.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Optional: ``pip install pypdf``.
"""

import os
import re
import sys
from collections.abc import Callable
from typing import Any

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

# --- Optional dependency ---
try:
    from pypdf import PdfReader as _PdfReader  # type: ignore

    HAS_PYPDF = True
except ImportError:
    _PdfReader = None  # type: ignore[assignment]
    HAS_PYPDF = False

# Injectable seam used by tests (defaults to the real reader when available).
PdfReader: Callable[[str], Any] | None = _PdfReader if HAS_PYPDF else None

MY_SCRIPT_SETTINGS = [
    {"key": "max_pdfs", "type": "number", "label": "Max PDFs per run", "default": 3},
    {
        "key": "heading_detection",
        "type": "toggle",
        "label": "ALL-CAPS lines become headings",
        "default": True,
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()

_WIKILINK_RE = re.compile(r"\[\[([^\]]+?\.pdf)\]\]", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\]\(([^)]+?\.pdf)\)", re.IGNORECASE)
_CAPS_RE = re.compile(r"^[A-Z0-9 ,'&\-]{4,60}$")


# --- Pure core ---


def find_pdf_links(content: str) -> list[str]:
    """Unique vault-relative PDF paths referenced by the note, in order."""
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.finditer(content):
        seen.setdefault(match.group(1), None)
    for match in _MD_LINK_RE.finditer(content):
        seen.setdefault(match.group(1), None)
    return list(seen.keys())


def apply_heading_heuristic(page_text: str, enabled: bool) -> str:
    """Promote short ALL-CAPS lines to '## ' headings."""
    if not enabled:
        return page_text.strip()
    out: list[str] = []
    for line in page_text.splitlines():
        stripped = line.strip()
        if stripped and _CAPS_RE.match(stripped) and not stripped.endswith("."):
            out.append(f"## {stripped.title()}")
        else:
            out.append(line.rstrip())
    return "\n".join(out).strip()


def render_extracted_note(pdf_rel: str, pages: list[str], headings_enabled: bool) -> str:
    """Build the target markdown for one PDF."""
    base = os.path.splitext(os.path.basename(pdf_rel))[0]
    lines: list[str] = [
        "---",
        f'source_pdf: "[[{os.path.basename(pdf_rel)}]]"',
        "type: pdf-extract",
        "---",
        "",
        f"# {base}",
        "",
    ]
    for idx, raw in enumerate(pages, start=1):
        lines.append(f"## Page {idx}" if not headings_enabled else f"### Page {idx}")
        lines.append("")
        lines.append(apply_heading_heuristic(raw, headings_enabled))
        lines.append("")
    return "\n".join(lines)


def sibling_note_path(pdf_rel: str) -> str:
    """'Docs/Doc.pdf' -> 'Docs/Doc (Extracted).md'."""
    folder = os.path.dirname(pdf_rel)
    name = os.path.splitext(os.path.basename(pdf_rel))[0]
    return os.path.join(folder, f"{name} (Extracted).md")


def unique_target(obsidian: ObsidianPluginDevPythonToJS, target: str) -> str:
    """Append -2, -3… before '.md' until a free path is found."""
    candidate = target
    counter = 2
    while obsidian.check_path_exists(candidate):
        stem, ext = os.path.splitext(target)
        candidate = f"{stem} ({counter}){ext}"
        counter += 1
    return candidate


def extract_pages(pdf_abs_path: str) -> list[str]:
    """Text of each page via the (injectable) PdfReader."""
    if PdfReader is None:
        raise RuntimeError("pypdf unavailable")
    reader = PdfReader(pdf_abs_path)
    return [(page.extract_text() or "") for page in reader.pages]


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    try:
        settings = obsidian.get_script_settings()
        max_pdfs = int(settings.get("max_pdfs", MY_SCRIPT_SETTINGS[0]["default"]))
        headings_enabled = bool(settings.get("heading_detection", MY_SCRIPT_SETTINGS[1]["default"]))
    except ObsidianCommError:
        max_pdfs, headings_enabled = 3, True

    if PdfReader is None:
        obsidian.show_notification("Missing dependency. Run: pip install pypdf", 8000)
        return

    content = obsidian.get_active_note_content(return_format="string") or ""
    pdf_links = find_pdf_links(content)[: max(max_pdfs, 0)]
    if not pdf_links:
        obsidian.show_notification("No PDF links found in this note.", 4000)
        return

    try:
        vault_abs = obsidian.get_current_vault_absolute_path()
    except ObsidianCommError as e:
        print(f"ERROR: vault path unavailable: {e}", file=sys.stderr)
        return

    created, failed = [], 0
    for pdf_rel in pdf_links:
        target = unique_target(obsidian, sibling_note_path(pdf_rel))
        try:
            pages = extract_pages(os.path.join(vault_abs, pdf_rel))
            obsidian.create_note(target, render_extracted_note(pdf_rel, pages, headings_enabled))
            created.append(target)
        except Exception as e:  # unreadable file, bad path, decode issues…
            failed += 1
            print(f"WARNING: could not extract '{pdf_rel}': {e}", file=sys.stderr)

    summary = f"{len(created)} extracted"
    if failed:
        summary += f", {failed} failed"
    obsidian.show_notification(summary, 5000)


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
