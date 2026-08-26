"""
Obsidian Python Bridge Script: Concise English Word Definition

Select an English word in the active note, run the script, and get its
definition from the free dictionaryapi.dev API inside an Obsidian notification.

Kept intentionally small (it is the repo's "minimal example"), but now follows
the recommended bridge script structure and exposes its logic as testable
functions:

- ``fetch_definition(word)`` — pure-ish network call, no bridge dependency.
- ``main()``                 — bridge orchestration (selection -> notification).

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x, 'requests' (`pip install requests`)
"""

import os
import sys

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
    print(
        "Please ensure the library is accessible via PYTHONPATH or in the script's directory.",
        file=sys.stderr,
    )
    sys.exit(1)

# --- Event helper: prefer the modern API, degrade gracefully ---
try:
    from ObsidianPluginDevPythonToJS import is_handling_event
except ImportError:

    def is_handling_event() -> bool:  # type: ignore[misc]
        return bool(os.environ.get("OBSIDIAN_EVENT_NAME"))


# --- Event Handling ---
# Recommended even for scripts not designed for events: exit early instead of
# running side effects when spawned by a vault event.
if is_handling_event():
    sys.exit(0)

# --- Settings Definition & Discovery Handling (MANDATORY structure) ---
MY_SCRIPT_SETTINGS: list = []
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()

# --- Constants ---
DICTIONARY_API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
API_TIMEOUT_SECONDS = 5
DEFINITION_MAX_LENGTH = 400
NOTIFICATION_DURATION_MS = 10000


def truncate(text: str, limit: int = DEFINITION_MAX_LENGTH) -> str:
    """Truncate *text* to *limit* characters, appending '...' when cut."""
    return text[:limit] + ("..." if len(text) > limit else "")


def fetch_definition(word: str) -> str:
    """Fetch the first definition of *word* from dictionaryapi.dev.

    Raises ``requests.RequestException`` on network failure — callers decide
    how to surface the error. Unexpected payload shapes degrade to a friendly
    message instead of crashing.
    """
    response = requests.get(
        DICTIONARY_API_URL.format(word=word.lower()), timeout=API_TIMEOUT_SECONDS
    )
    if response.status_code != 200:
        return f"'{word}' not found or API error."
    try:
        return response.json()[0]["meanings"][0]["definitions"][0]["definition"]
    except (IndexError, KeyError, TypeError):
        return "Definition format unclear."


def main() -> None:
    """Bridge orchestration: read selection, fetch definition, notify."""
    obsidian = ObsidianPluginDevPythonToJS()

    word = obsidian.get_selected_text().strip()
    if not word:
        # No selection: exit silently, exactly like the original concise version.
        sys.exit(0)

    definition = fetch_definition(word)
    obsidian.show_notification(
        f"**{word}:**\n{truncate(definition)}",
        NOTIFICATION_DURATION_MS,
    )


if __name__ == "__main__":
    try:
        main()
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
