"""
Obsidian Python Bridge Script: OCR Image Transcriber (optional-dep showcase)

Scans the active note for embedded images (``![[shot.png]]`` or
``![](folder/shot.png)``), runs them through **Tesseract OCR** and inserts an
idempotent transcription callout right under each embed:

    ![[scan.png]]
    <!-- ocr:start -->
    > Recognised text:
    > ```
    > hello world
    > ```
    <!-- ocr:end -->

`pytesseract` (+ Pillow + the tesseract binary) are OPTIONAL dependencies —
missing ones produce a helpful hint, not a traceback. The OCR engine itself
is an injectable function so tests never need Tesseract installed.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Optional: ``pip install pytesseract pillow`` and a system tesseract binary.
"""

import os
import re
import sys
from collections.abc import Callable

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

# --- Optional dependencies ---
try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore

    HAS_OCR = True
except ImportError:
    pytesseract = None  # type: ignore[assignment]
    HAS_OCR = False


MY_SCRIPT_SETTINGS = [
    {"key": "language", "type": "text", "label": "Tesseract language(s)", "default": "eng"},
    {"key": "max_images", "type": "number", "label": "Max images per run", "default": 5},
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()

OCR_START = "<!-- ocr:start -->"
OCR_END = "<!-- ocr:end -->"

_EMBED_WIKI_RE = re.compile(r"!\[\[([^\]]+\.(?:png|jpe?g|gif|bmp|webp))\]\]", re.IGNORECASE)
_EMBED_MD_RE = re.compile(r"!\[[^\]]*\]\(([^)]+\.(?:png|jpe?g|gif|bmp|webp))\)", re.IGNORECASE)

# Injectable OCR engine (tests replace it; runtime uses real Tesseract).
transcribe_image: Callable[..., str]


def _default_transcribe(abs_path: str, language: str = "eng") -> str:
    return pytesseract.image_to_string(Image.open(abs_path), lang=language)


if HAS_OCR:
    transcribe_image = _default_transcribe
else:  # pragma: no cover - placeholder replaced at runtime by dependency install

    def transcribe_image(abs_path: str, language: str = "eng") -> str:
        raise RuntimeError("pytesseract unavailable")


# --- Pure core ---


def strip_previous_transcriptions(content: str) -> str:
    pattern = re.compile(re.escape(OCR_START) + r".*?" + re.escape(OCR_END) + r"\n?", re.DOTALL)
    return pattern.sub("", content)


def find_image_lines(content: str) -> list[tuple[int, str]]:
    """(line_index, image_path) pairs, wikilinks first-come-first-served."""
    results: list[tuple[int, str]] = []
    seen: set[str] = set()
    for idx, line in enumerate(content.split("\n")):
        match = _EMBED_WIKI_RE.search(line) or _EMBED_MD_RE.search(line)
        if match and match.group(1) not in seen:
            seen.add(match.group(1))
            results.append((idx, match.group(1)))
    return results


def render_transcription(text: str) -> str:
    cleaned = text.strip() or "(no text recognised)"
    quoted = "\n".join(f"> {line}" for line in cleaned.split("\n"))
    return f"{OCR_START}\n> Recognised text:\n> ```\n{quoted}\n> ```\n{OCR_END}\n"


def insert_transcriptions(content: str, results: list[tuple[int, str]]) -> tuple[str, int]:
    """Insert rendered blocks under their image lines, bottom-up."""
    lines = content.split("\n")
    for idx, rendered in sorted(results, key=lambda pair: pair[0], reverse=True):
        lines.insert(idx + 1, rendered)
    return "\n".join(lines), len(results)


def process_note(
    content: str, engine: Callable[..., str], language: str, max_images: int
) -> tuple[str, int, int]:
    """Full pure pipeline. Returns (new_content, n_done, n_failed)."""
    cleaned = strip_previous_transcriptions(content)
    targets = find_image_lines(cleaned)[: max(max_images, 0)]
    if not targets:
        return content, 0, 0

    insertions: list[tuple[int, str]] = []
    failures = 0
    for idx, rel_path in targets:
        try:
            text = engine(rel_path, language)
            insertions.append((idx, render_transcription(text)))
        except Exception as e:
            failures += 1
            print(f"WARNING: OCR failed for '{rel_path}': {e}", file=sys.stderr)
            insertions.append((idx, render_transcription("(unreadable)")))

    new_content, done = insert_transcriptions(cleaned, insertions)
    return new_content, done, failures


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    global transcribe_image

    try:
        settings = obsidian.get_script_settings()
        language = str(settings.get("language", MY_SCRIPT_SETTINGS[0]["default"]))
        max_images = int(settings.get("max_images", MY_SCRIPT_SETTINGS[1]["default"]))
    except ObsidianCommError:
        language, max_images = "eng", 5

    if not HAS_OCR:
        obsidian.show_notification("Missing deps. Run: pip install pytesseract pillow", 8000)
        return

    abs_path = obsidian.get_active_note_absolute_path()
    content = obsidian.get_active_note_content(return_format="string") or ""

    vault_abs = ""
    try:
        vault_abs = obsidian.get_current_vault_absolute_path()
    except ObsidianCommError:
        pass  # Engine receives relative paths as-is in that case.

    def engine(_rel_path: str, lang: str = "eng") -> str:
        real_path = os.path.join(vault_abs, _rel_path) if vault_abs else _rel_path
        return _default_transcribe(real_path, lang)

    new_content, done, failed = process_note(content, engine, language, max_images)
    if done == 0:
        obsidian.show_notification("No image embeds found.", 4000)
        return

    obsidian.modify_note_content(abs_path, new_content)
    msg = f"OCR done on {done} image(s)"
    if failed:
        msg += f" ({failed} unreadable)"
    obsidian.show_notification(msg, 5000)


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
