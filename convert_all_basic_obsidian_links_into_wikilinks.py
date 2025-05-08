# -*- coding: utf-8 -*-
"""
Obsidian Python Bridge Script: Simple Link to Wikilink Converter

This script finds simple Obsidian links like [[My Note]] in the currently
active note and converts them to wikilinks like [[My Note|My Note]].
It preserves the YAML frontmatter block.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x
- 'requests' library (`pip install requests`)
"""

import sys
import os
import re
import json # Imported for potential future use, not directly used now
from typing import List, Union # For type hinting

# --- Library Import ---
# Ensure the Obsidian Python Bridge library is accessible
# Recommended: Use the plugin's "Auto-set PYTHONPATH" setting (enabled by default)
# Alternative: Copy ObsidianPluginDevPythonToJS.py into the same folder as this script
try:
    from ObsidianPluginDevPythonToJS import (
        ObsidianPluginDevPythonToJS, ObsidianCommError,
        define_settings, _handle_cli_args
    )
except ImportError:
    print("ERROR: ObsidianPluginDevPythonToJS.py library not found.", file=sys.stderr)
    print("Please ensure the library is accessible via PYTHONPATH or in the script's directory.", file=sys.stderr)
    sys.exit(1)

# --- Event Handling ---
# Check if the script was triggered by an Obsidian event and exit if so.
# This prevents the main logic from running unintentionally.
event_name_from_env = os.environ.get("OBSIDIAN_EVENT_NAME")
if event_name_from_env:
    print(f"INFO: Script launched by event '{event_name_from_env}', exiting.", file=sys.stderr)
    # If needed, add event-specific logic here based on event_name_from_env
    # and the payload in os.environ.get("OBSIDIAN_EVENT_PAYLOAD", "{}")
    sys.exit(0)

# --- Settings Definition & Discovery Handling (Recommended Structure) ---
# Define script-specific settings (empty list if none).
# This is necessary for the plugin to correctly handle the script during
# its settings discovery phase (--get-settings-json).
MY_SCRIPT_SETTINGS: list = []
define_settings(MY_SCRIPT_SETTINGS)

# Handle the --get-settings-json argument.
# This function MUST be called after define_settings() and before the main logic.
# It will print the settings JSON (if any) and exit if the argument is present.
_handle_cli_args()

# --- Core Link Conversion Logic (Original logic, unchanged) ---
def replace_simple_links_with_wikilinks(content_line: str) -> str:
    """
    Uses regex to find [[Simple Links]] and replace them with [[Simple Links|Simple Links]].
    It avoids replacing links that already contain a pipe '|'.

    Args:
        content_line (str): A single line of text from the note.

    Returns:
        str: The line with simple links converted to wikilinks.
    """
    # Regex to capture [[simple link]] that does not already contain a '|'
    # - \[\[   : Matches the opening double square brackets
    # - ([^\|\]]+) : Captures group 1: one or more characters that are NOT a pipe '|' or closing bracket ']'
    # - \]\]   : Matches the closing double square brackets
    pattern = r"\[\[([^\|\]]+)\]\]"

    # Replacement function used by re.sub
    def replacer(match: re.Match) -> str:
        # Get the captured link text (content inside the brackets)
        link = match.group(1)
        # Return the wikilink format
        return f"[[{link}|{link}]]"

    # Substitute all occurrences in the line using the replacer function
    return re.sub(pattern, replacer, content_line)

# --- Main Execution Block ---
# This code runs only if the script is executed normally (not via event or discovery).
if __name__ == "__main__":
    print("--- Starting Simple Link to Wikilink Conversion Script ---")
    obsidian: ObsidianPluginDevPythonToJS | None = None # Initialize to None for the finally block

    try:
        # Initialize the Obsidian client library (after initial checks)
        # This connects to the Obsidian Python Bridge plugin via HTTP
        obsidian = ObsidianPluginDevPythonToJS()
        print("INFO: Obsidian client initialized.")

        # --- Get Active Note Path ---
        try:
            # Retrieve the absolute file path of the currently active note
            note_path_abs = obsidian.get_active_note_absolute_path()
            print(f"INFO: Processing note: {note_path_abs}")
        except ObsidianCommError as e:
            # Handle errors if no note is active or communication fails
            print(f"ERROR: Could not get active note path: {e}", file=sys.stderr)
            # Attempt to show a notification, but might fail if client init failed partially
            try: obsidian.show_notification(f"Error: Active note path not found. {e}", 5000)
            except: pass # Fail silently if obsidian object isn't fully functional
            sys.exit(1) # Exit script on critical error

        # --- Get Note Content (as lines) ---
        try:
            # Request content as a list of lines, which suits the existing loop structure
            lines: Union[List[str], str] = obsidian.get_active_note_content(return_format='lines') # Type hint helps clarity
            if not isinstance(lines, list):
                 # This case should ideally be caught by ObsidianCommError if the API returns unexpected data,
                 # but added as a safeguard. get_active_note_content returns None if no active note.
                 if lines is None:
                     raise ObsidianCommError("Active note content received as None.")
                 else:
                     raise ObsidianCommError(f"Expected list of lines, got {type(lines).__name__}.")
            print(f"INFO: Note content read ({len(lines)} lines).")
        except ObsidianCommError as e:
            # Handle errors during content retrieval
            print(f"ERROR: Could not get note content: {e}", file=sys.stderr)
            try: obsidian.show_notification(f"Error: Failed to read content. {e}", 5000)
            except: pass
            sys.exit(1)
        except ValueError as e:
             # Handle potential error if return_format was somehow invalid (shouldn't happen here)
             print(f"ERROR: Invalid return_format used: {e}", file=sys.stderr)
             try: obsidian.show_notification(f"Error: Invalid return format. {e}", 5000)
             except: pass
             sys.exit(1)

        # --- Process Content (Original logic, unchanged) ---
        print("INFO: Searching for simple links and replacing them...")
        new_content_lines: List[str] = []
        in_frontmatter: bool = False
        frontmatter_boundary_count: int = 0
        content_changed: bool = False # Flag to track if any replacements were made

        # Basic frontmatter detection and applying the transformation line by line
        # NOTE: This detection assumes '---' only appears at the start/end of the frontmatter block.
        for i, line in enumerate(lines):
            original_line: str = line
            processed_line: str = line # Start with the original line

            # Detect frontmatter boundaries
            if line.strip() == "---":
                if i == 0: # First line is '---'
                    in_frontmatter = True
                    frontmatter_boundary_count += 1
                elif in_frontmatter and frontmatter_boundary_count == 1: # Found the closing '---'
                    in_frontmatter = False
                    frontmatter_boundary_count += 1
                # Ignore potential '---' further down in the content

            # Apply transformation only if not currently inside the detected frontmatter block
            # (frontmatter_boundary_count != 1 means we are either before the first '---' or after the second '---')
            if not in_frontmatter and frontmatter_boundary_count != 1:
                processed_line = replace_simple_links_with_wikilinks(line)
                # Check if the line was actually changed
                if processed_line != original_line:
                    content_changed = True

            # Add the (potentially processed) line to the new content list
            new_content_lines.append(processed_line)
        # --- End of original processing logic ---

        # --- Write Modified Content (using V2 API) ---
        if content_changed:
            print("INFO: Content modified, writing back via Obsidian API...")
            # Reconstruct the full content string for the API
            # Use '\n' as the standard newline separator; Obsidian handles OS differences.
            new_content_string: str = "\n".join(new_content_lines)
            try:
                # Use the modify_note_content method with the absolute path
                obsidian.modify_note_content(note_path_abs, new_content_string)
                print("INFO: Modification request sent successfully.")
                obsidian.show_notification("Simple links converted to wikilinks!", 4000)
            except ObsidianCommError as e:
                # Handle errors during the write operation
                print(f"ERROR: Failed to write note content: {e}", file=sys.stderr)
                try: obsidian.show_notification(f"Error saving changes: {e}", 5000)
                except: pass
                sys.exit(1) # Exit if saving failed
        else:
            # Inform the user if no changes were needed
            print("INFO: No simple links found to convert.")
            obsidian.show_notification("No simple links needed conversion.", 3000)

        print("--- Wikilink Conversion Script Finished ---")

    # --- General Error Handling ---
    except ObsidianCommError as e:
        # Catch communication errors during initialization or other unexpected API calls
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        if obsidian: # Try to notify if the client object exists
            try: obsidian.show_notification(f"Bridge Error: {e}", 5000)
            except: pass
        sys.exit(1) # Exit on critical errors
    except Exception as e:
        # Catch any other unexpected Python errors
        print(f"ERROR: Unexpected Python Error: {type(e).__name__}: {e}", file=sys.stderr)
        # Include traceback for detailed debugging if needed
        import traceback
        traceback.print_exc(file=sys.stderr)
        if obsidian:
            try: obsidian.show_notification(f"Script Error: {e}", 5000)
            except: pass
        sys.exit(1) # Exit on critical errors
