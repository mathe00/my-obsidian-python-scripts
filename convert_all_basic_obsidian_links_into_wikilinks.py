"""
Obsidian Python Bridge Script: Simple Link to Wikilink Converter

This script finds simple Obsidian links like ``[[My Note]]`` in the currently
active note and converts them to piped wikilinks like ``[[My Note|My Note]]``.
It preserves the YAML frontmatter block.

Logic is split into testable units:

- :func:`replace_simple_links_with_wikilinks` — pure per-line regex transform.
- :func:`process_lines`                       — pure whole-note transform
  (frontmatter-aware), returns ``(new_lines, changed)``.
- :func:`run`                                 — bridge orchestration, takes an
  already-built client so tests can inject a fake.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x
- 'requests' library (`pip install requests`)
"""

import os
import re
import sys

# --- Library Import ---
# Ensure the Obsidian Python Bridge library is accessible.
# Recommended: use the plugin's "Auto-set PYTHONPATH" setting (enabled by default).
# Alternative: copy ObsidianPluginDevPythonToJS.py next to this script.
try:
    from ObsidianPluginDevPythonToJS import (
        ObsidianCommError,
        ObsidianPluginDevPythonToJS,
        _handle_cli_args,
        define_settings,
    )
except ImportError:
    print("ERROR: ObsidianPluginDevPythonToJS.py library not found.", file=sys.stderr)
    print(
        "Please ensure the library is accessible via PYTHONPATH or in the script's directory.",
        file=sys.stderr,
    )
    sys.exit(1)

# --- Event helper: prefer the modern API, degrade gracefully ---
# Recent OPB versions expose is_handling_event(); some builds/shims do not
# re-export it yet, in which case we fall back to reading the environment.
try:
    from ObsidianPluginDevPythonToJS import is_handling_event
except ImportError:
    from obsidian_python_bridge._events import is_handling_event  # type: ignore[no-redef]

if "is_handling_event" not in globals():

    def is_handling_event() -> bool:  # type: ignore[misc]
        return bool(os.environ.get("OBSIDIAN_EVENT_NAME"))


# --- Event Handling ---
event = is_handling_event()
if event:
    print(f"INFO: Script launched by event '{event}', exiting.", file=sys.stderr)
    sys.exit(0)

# --- Settings Definition & Discovery Handling (MANDATORY structure) ---
MY_SCRIPT_SETTINGS: list = []
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()


# --- Core Link Conversion Logic (pure functions) ---
def replace_simple_links_with_wikilinks(content_line: str) -> str:
    """Convert every ``[[Simple Link]]`` of *content_line* to ``[[Link|Link]]``.

    Links that already contain a pipe ``|`` are left untouched.

    Args:
        content_line: A single line of text from the note.

    Returns:
        The line with simple links converted to wikilinks.
    """
    # - \\[\\[          : opening double square brackets
    # - ([^|\\]]+)      : capture — one or more chars that are NOT '|' or ']'
    # - \\]\\]          : closing double square brackets
    pattern = r"\[\[([^\|\]]+)\]\]"

    def replacer(match: re.Match[str]) -> str:
        link = match.group(1)
        return f"[[{link}|{link}]]"

    return re.sub(pattern, replacer, content_line)


def process_lines(lines: list[str]) -> tuple[list[str], bool]:
    """Apply :func:`replace_simple_links_with_wikilinks` outside the frontmatter.

    Frontmatter detection assumes ``---`` only appears as first line and as
    the closing delimiter of the frontmatter block; later horizontal rules
    are ignored.

    Args:
        lines: Note content split into lines.

    Returns:
        ``(new_lines, content_changed)``.
    """
    new_content_lines: list[str] = []
    in_frontmatter = False
    frontmatter_boundary_count = 0
    content_changed = False

    for i, line in enumerate(lines):
        original_line = line

        # Detect frontmatter boundaries ('---' at index 0 opens, second closes).
        if line.strip() == "---":
            if i == 0:
                in_frontmatter = True
                frontmatter_boundary_count += 1
            elif in_frontmatter and frontmatter_boundary_count == 1:
                in_frontmatter = False
                frontmatter_boundary_count += 1
            # '---' further down in the body is ignored.

        # Transform only outside the detected frontmatter block.
        if not in_frontmatter and frontmatter_boundary_count != 1:
            processed_line = replace_simple_links_with_wikilinks(line)
            if processed_line != original_line:
                content_changed = True
        else:
            processed_line = line

        new_content_lines.append(processed_line)

    return new_content_lines, content_changed


# --- Orchestration (bridge-dependent, injectable for tests) ---
def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    """Run the conversion on the currently active note using *obsidian*."""
    # --- Get Active Note Path ---
    try:
        note_path_abs = obsidian.get_active_note_absolute_path()
        print(f"INFO: Processing note: {note_path_abs}")
    except ObsidianCommError as e:
        print(f"ERROR: Could not get active note path: {e}", file=sys.stderr)
        try:
            obsidian.show_notification(f"Error: Active note path not found. {e}", 5000)
        except Exception:
            pass  # best-effort notification only
        sys.exit(1)

    # --- Get Note Content (as lines) ---
    try:
        lines = obsidian.get_active_note_content(return_format="lines")
        if lines is None:
            raise ObsidianCommError("Active note content received as None.")
        if not isinstance(lines, list):
            raise ObsidianCommError(f"Expected list of lines, got {type(lines).__name__}.")
        print(f"INFO: Note content read ({len(lines)} lines).")
    except ObsidianCommError as e:
        print(f"ERROR: Could not get note content: {e}", file=sys.stderr)
        try:
            obsidian.show_notification(f"Error: Failed to read content. {e}", 5000)
        except Exception:
            pass
        sys.exit(1)

    # --- Process Content ---
    print("INFO: Searching for simple links and replacing them...")
    new_content_lines, content_changed = process_lines(lines)

    # --- Write Modified Content (V2 API) ---
    if content_changed:
        print("INFO: Content modified, writing back via Obsidian API...")
        # '\\n' as standard separator; Obsidian handles OS differences.
        new_content_string = "\n".join(new_content_lines)
        try:
            obsidian.modify_note_content(note_path_abs, new_content_string)
            print("INFO: Modification request sent successfully.")
            obsidian.show_notification("Simple links converted to wikilinks!", 4000)
        except ObsidianCommError as e:
            print(f"ERROR: Failed to write note content: {e}", file=sys.stderr)
            try:
                obsidian.show_notification(f"Error saving changes: {e}", 5000)
            except Exception:
                pass
            sys.exit(1)
    else:
        print("INFO: No simple links found to convert.")
        obsidian.show_notification("No simple links needed conversion.", 3000)


# --- Main Execution Block ---
if __name__ == "__main__":
    print("--- Starting Simple Link to Wikilink Conversion Script ---")
    try:
        obsidian = ObsidianPluginDevPythonToJS()
        print("INFO: Obsidian client initialized.")
        run(obsidian)
        print("--- Wikilink Conversion Script Finished ---")

    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected Python Error: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
