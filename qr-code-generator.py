"""
Obsidian Python Bridge Script: QR Code Generator (optional-dep showcase)

Turn selected text (or a modal prompt) into a QR code PNG dropped into your
attachments folder and embedded into the note — `qrcode` is an OPTIONAL
dependency: without it you get a friendly install hint instead of a crash.

Also shows off the bridge's filesystem actions (`check_path_exists`,
`create_folder`) plus `get_current_vault_absolute_path`.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Optional: ``pip install qrcode[pil]``.
"""

import hashlib
import os
import re
import sys
import unicodedata

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
    import qrcode  # type: ignore

    HAS_QRCODE = True
except ImportError:
    qrcode = None  # type: ignore[assignment]
    HAS_QRCODE = False

MY_SCRIPT_SETTINGS = [
    {
        "key": "attachments_folder",
        "type": "text",
        "label": "Attachments folder (vault-relative)",
        "default": "Attachments",
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()


# --- Pure core ---


def slugify(text: str, max_len: int = 32) -> str:
    """ASCII-safe, lowercase, dashed filename base from arbitrary text."""
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len].rstrip("-") or "qr"


def unique_filename(text: str) -> str:
    """Stable name: slug + 8-char content hash so identical input overwrites itself."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{slugify(text)}-{digest}.png"


def build_embed_markdown(filename: str) -> str:
    """Obsidian wiki-embed for an attachment."""
    return f"![[{filename}]]"


def make_qr_png(text: str, png_abs_path: str) -> bool:
    """Render the PNG using the optional qrcode lib. Injectable in tests."""
    if not HAS_QRCODE:
        return False
    img = qrcode.make(text)
    img.save(png_abs_path)
    return True


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    try:
        settings = obsidian.get_script_settings()
        folder_rel = str(
            settings.get("attachments_folder", MY_SCRIPT_SETTINGS[0]["default"])
        ).strip("/\\")
    except ObsidianCommError:
        folder_rel = "Attachments"

    if not HAS_QRCODE:
        obsidian.show_notification("Missing dependency. Run: pip install qrcode[pil]", 8000)
        return

    text = obsidian.get_selected_text().strip()
    from_selection = bool(text)
    if not from_selection:
        try:
            text = obsidian.request_user_input(
                script_name="QR Code",
                input_type="text",
                message="Text or URL to encode:",
            )
            text = (text or "").strip()
        except ObsidianCommError:
            text = ""
    if not text:
        obsidian.show_notification("Nothing to encode.", 4000)
        return

    filename = unique_filename(text)
    try:
        vault_abs = obsidian.get_current_vault_absolute_path()
    except ObsidianCommError as e:
        print(f"ERROR: vault path unavailable: {e}", file=sys.stderr)
        return

    folder_abs = os.path.join(vault_abs, folder_rel)
    try:
        if not obsidian.check_path_exists(folder_rel):
            obsidian.create_folder(folder_rel)
    except ObsidianCommError as e:
        print(
            f"WARNING: bridge folder ops failed ({e}); falling back to direct makedirs.",
            file=sys.stderr,
        )
        os.makedirs(folder_abs, exist_ok=True)

    png_abs = os.path.join(folder_abs, filename)
    if not make_qr_png(text, png_abs):
        obsidian.show_notification("PNG rendering failed.", 5000)
        return

    embed = build_embed_markdown(filename)
    if from_selection:
        obsidian.replace_selected_text(embed)
    else:
        abs_note = obsidian.get_active_note_absolute_path()
        content = obsidian.get_active_note_content(return_format="string") or ""
        obsidian.modify_note_content(abs_note, content.rstrip("\n") + "\n\n" + embed + "\n")

    obsidian.show_notification(f"QR saved → {folder_rel}/{filename}", 5000)


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
