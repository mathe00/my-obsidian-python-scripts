"""
Obsidian Python Bridge Script: CSV -> Markdown Table (data-wrangling flex)

POC: Python's batteries make tabular data trivial. Paste or select raw CSV
(commas, semicolons, tabs — auto-sniffed), run the script, get a properly
aligned Markdown table with pipes escaped, inserted right where your
selection was.

Priority order for input:
1. current selection (if it looks like CSV)
2. a paste-into-modal prompt
3. nothing → friendly exit

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x only (stdlib `csv`).
"""

import csv
import io
import os
import sys

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

MY_SCRIPT_SETTINGS = [
    {
        "key": "delimiter",
        "type": "text",
        "label": "Delimiter (empty = auto-detect)",
        "description": "Single character like ',' ';' '|' '\\t'. Empty means sniff.",
        "default": "",
    },
    {
        "key": "header_row",
        "type": "toggle",
        "label": "First row is a header",
        "default": True,
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()


# --- Pure core ---


def looks_like_csv(text: str) -> bool:
    """Cheap heuristic: >=2 lines sharing at least one common separator."""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    for sep in (",", ";", "\t", "|"):
        counts = {ln.count(sep) for ln in lines}
        if len(counts) == 1 and counts.pop() >= 1:
            return True
    return False


def sniff_delimiter(sample: str, override: str = "") -> str:
    """User override wins; otherwise csv.Sniffer on the sample (fallback ',')."""
    if override:
        return override[0]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def parse_csv(
    text: str, delimiter: str = "", has_header: bool = True
) -> tuple[list[str], list[list[str]]]:
    """Parse *text* into (headers, rows). Without header, columns get names C1..Cn."""
    delim = sniff_delimiter(text.strip().splitlines()[0] if text.strip() else "", delimiter)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    matrix = [row for row in reader if any(cell.strip() for cell in row)]
    if not matrix:
        return [], []

    width = max(len(r) for r in matrix)
    padded = [r + [""] * (width - len(r)) for r in matrix]

    if has_header:
        headers = padded[0]
        body = padded[1:]
    else:
        headers = [f"C{i + 1}" for i in range(width)]
        body = padded
    return headers, body


def escape_cell(cell: str) -> str:
    """Markdown-safe: pipes escaped, newlines flattened."""
    return cell.replace("|", "\\|").replace("\n", "<br>").strip()


def render_md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Aligned GitHub-flavoured markdown table."""
    if not headers:
        return ""
    header_cells = [escape_cell(h) for h in headers]
    widths = [len(h) for h in header_cells]
    rendered_rows = [[escape_cell(c) for c in row] for row in rows]
    for row in rendered_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    sep = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    lines = [fmt(header_cells), sep] + [fmt(r) for r in rendered_rows]
    return "\n".join(lines)


def transform_csv_to_table(text: str, delimiter: str = "", has_header: bool = True) -> str:
    headers, rows = parse_csv(text, delimiter, has_header)
    return render_md_table(headers, rows)


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    try:
        settings = obsidian.get_script_settings()
        delimiter = str(settings.get("delimiter", MY_SCRIPT_SETTINGS[0]["default"]))
        has_header = bool(settings.get("header_row", MY_SCRIPT_SETTINGS[1]["default"]))
    except ObsidianCommError:
        delimiter, has_header = "", True

    selection = obsidian.get_selected_text()

    if looks_like_csv(selection):
        source = "selection"
        raw_csv = selection
    else:
        try:
            raw_csv = obsidian.request_user_input(
                script_name="CSV to Markdown",
                input_type="textarea",
                message="Paste your CSV below:",
            )
            if not isinstance(raw_csv, str) or not raw_csv.strip():
                raise ObsidianCommError("cancelled or empty modal input")
            source = "modal"
        except ObsidianCommError:
            obsidian.show_notification("No usable CSV (selection empty / modal cancelled).", 4000)
            return

    table = transform_csv_to_table(raw_csv, delimiter, has_header)
    if not table:
        obsidian.show_notification("Could not parse any rows.", 4000)
        return

    if source == "selection":
        obsidian.replace_selected_text(table)
    else:
        abs_path = obsidian.get_active_note_absolute_path()
        content = obsidian.get_active_note_content(return_format="string") or ""
        updated = content.rstrip("\n") + "\n\n" + table + "\n"
        obsidian.modify_note_content(abs_path, updated)

    obsidian.show_notification(f"CSV converted ({source}) ✅", 4000)


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
