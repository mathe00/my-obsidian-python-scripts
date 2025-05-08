# -*- coding: utf-8 -*-
"""
Obsidian Python Bridge Script: Auto Linker (V2.3 - Simple Wikilinks)

This script automatically creates links in the currently active note.
It searches for text matching the titles (case-insensitive, accent-insensitive)
of other notes in the vault and converts them into one of three types based on settings:
- Wikilink with Alias: [[Note Title|Matched Text]]
- Simple Wikilink:     [[Note Title]]
- Markdown Link:       [Matched Text](Note%20Path.md)

Features:
- Preserves existing YAML frontmatter.
- Avoids creating links inside existing Markdown links, wikilinks, or code blocks.
- Configurable link type (Wikilink, Simple Wikilink, Markdown) via Plugin Settings.
- Configurable options for case preservation (for Alias/Markdown) and punctuation handling.
- Configurable option for ignoring accents during matching.
- Handles multi-word titles correctly, even mid-sentence with different casing/accents.
- Uses a robust matching and replacement strategy.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x
- 'requests' library (`pip install requests`)
"""

import sys
import os
import re
import unicodedata  # For handling accent removal
import json
import urllib.parse # For URL encoding markdown link paths
from typing import List, Optional, Tuple, Set, Dict, Union, NamedTuple # For type hinting

# --- Library Import ---
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
event_name_from_env = os.environ.get("OBSIDIAN_EVENT_NAME")
if event_name_from_env:
    print(f"INFO: Script launched by event '{event_name_from_env}', exiting.", file=sys.stderr)
    sys.exit(0)

# --- Settings Definition & Discovery Handling ---
MY_SCRIPT_SETTINGS = [
    {
        "key": "link_type",
        "type": "dropdown",
        "label": "Link Type",
        "description": "Choose the format for created links.",
        "default": "wikilink", # Default to piped wikilink
        "options": ["wikilink", "simple_wikilink", "markdown"] # Added simple_wikilink
    },
    {
        "key": "preserve_case",
        "type": "toggle",
        "label": "Preserve Original Case (for Alias/Markdown)",
        "description": "If enabled, link text keeps original casing (e.g., [[Title|oRiginal]] or [oRiginal](...). Ignored for Simple Wikilinks.",
        "default": True
    },
    {
        "key": "ignore_accents",
        "type": "toggle",
        "label": "Ignore Accents When Matching",
        "description": "If enabled, 'cafe' in your text can link to a note titled 'Café'.",
        "default": True
    },
    {
        "key": "match_punctuation",
        "type": "toggle",
        "label": "Match Adjacent Punctuation",
        "description": "If enabled, attempts to include punctuation like '.' or ',' immediately following the matched text outside the link.",
        "default": True
    }
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args() # Handles --get-settings-json and exits if present

# --- Core Logic Functions ---

def remove_accents(text: str) -> str:
    """Normalizes string by removing accents."""
    if not isinstance(text, str): return text
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

def is_inside_link_or_code(index: int, content: str) -> bool:
    """
    Checks if the character at the given index is already inside a known
    link structure ([[...]], [...](...)) or code block (`...`, ```...```).
    Uses simplified checks.
    """
    # Check [[...]]
    link_start = content.rfind("[[", 0, index)
    link_end = content.find("]]", index)
    if link_start != -1 and link_end != -1 and link_start < index < link_end: return True
    # Check [...](...)
    paren_start = content.rfind("(", 0, index)
    paren_end = content.find(")", index)
    if paren_start != -1 and paren_end != -1:
         bracket_end = content.rfind("]", 0, paren_start)
         if bracket_end != -1 and bracket_end < paren_start:
              if paren_start < index < paren_end: return True
    # Check `...`
    if content[:index].count('`') % 2 != 0:
        next_backtick = content.find("`", index)
        if next_backtick != -1: return True
    # Check ```...```
    block_start = content.rfind("```", 0, index)
    if block_start != -1:
        block_end = content.find("```", block_start + 3)
        if block_end == -1 or index < block_end: return True
    return False

# Helper class to store match information
class MatchInfo(NamedTuple):
    start: int
    end: int
    title: str # Canonical title (with original accents/case)
    matched_text: str # Text found in the document (original accents/case)
    trailing_char: str # Character(s) immediately following the match

def create_links_v3( # Renamed function slightly for clarity
    original_body: str,
    titles_set: Set[str],
    title_to_path_map: Dict[str, str],
    link_type_pref: str,
    preserve_case: bool,
    ignore_accents: bool,
    match_punctuation: bool
    ) -> Tuple[str, bool]:
    """
    Processes the main content body to find text matching note titles and converts
    them to the specified link type (wikilink, simple_wikilink, markdown).
    Uses a find-all-then-replace strategy for robustness.

    Args:
        original_body (str): The main body content of the note.
        titles_set (Set[str]): A set of all unique note titles in the vault.
        title_to_path_map (Dict[str, str]): Mapping from note title to its relative path.
        link_type_pref (str): Preferred link type ("wikilink", "simple_wikilink", "markdown").
        preserve_case (bool): Whether to keep the original casing in the link text (for wikilink/markdown).
        ignore_accents (bool): Whether to ignore accents during matching.
        match_punctuation (bool): Whether to match text followed by punctuation.

    Returns:
        Tuple[str, bool]: A tuple containing (processed_content, content_was_changed).
    """
    if not original_body or not titles_set:
        return original_body, False

    search_body = remove_accents(original_body) if ignore_accents else original_body
    all_matches: List[MatchInfo] = []

    # 1. Find all potential matches
    sorted_titles = sorted(list(titles_set), key=len, reverse=True)
    for title in sorted_titles:
        if not title: continue

        normalized_title = remove_accents(title) if ignore_accents else title
        title_re = re.escape(normalized_title)

        trailing_char_pattern = r"([\s.,;!?()]|$)" if match_punctuation else r"(\s|$|\b)"
        regex_pattern = rf"\b({title_re}){trailing_char_pattern}"
        regex = re.compile(regex_pattern, re.IGNORECASE)

        for match in regex.finditer(search_body):
            start_idx, end_idx = match.span()
            title_end_idx = start_idx + len(match.group(1))
            original_matched_text = original_body[start_idx:title_end_idx]
            original_trailing_char = original_body[title_end_idx:end_idx]

            all_matches.append(MatchInfo(
                start=start_idx,
                end=end_idx,
                title=title, # Store the canonical title
                matched_text=original_matched_text,
                trailing_char=original_trailing_char
            ))

    # 2. Filter and select valid, non-overlapping matches
    if not all_matches: return original_body, False
    all_matches.sort(key=lambda m: (m.start, -len(m.matched_text)))

    valid_matches: List[MatchInfo] = []
    last_processed_end_index = -1

    for match in all_matches:
        if match.start < last_processed_end_index: continue
        check_index = match.start + len(match.matched_text) // 2
        if is_inside_link_or_code(check_index, original_body): continue

        valid_matches.append(match)
        last_processed_end_index = match.end

    # 3. Build the new string using valid matches
    if not valid_matches: return original_body, False

    new_content_parts = []
    current_index = 0
    content_changed = False

    for match in valid_matches:
        # Add the text segment before this match
        new_content_parts.append(original_body[current_index:match.start])

        # Construct the link based on preference
        link_text = match.matched_text if preserve_case else match.title
        link_target = match.title # Canonical title for linking

        if link_type_pref == "markdown":
            relative_path = title_to_path_map.get(match.title)
            if relative_path:
                encoded_path = urllib.parse.quote(relative_path)
                link_string = f"[{link_text}]({encoded_path})"
            else:
                print(f"WARNING: Path not found for title '{match.title}' for Markdown link.", file=sys.stderr)
                link_string = match.matched_text # Fallback
        elif link_type_pref == "simple_wikilink":
             # Simple wikilink uses the canonical title directly
             link_string = f"[[{link_target}]]"
        else: # Default to piped wikilink
            link_string = f"[[{link_target}|{link_text}]]"

        # Add the created link and its original trailing character
        new_content_parts.append(link_string)
        new_content_parts.append(match.trailing_char)

        # Update index and flag
        current_index = match.end
        content_changed = True

    # Add any remaining text after the last match
    new_content_parts.append(original_body[current_index:])

    return "".join(new_content_parts), content_changed


def split_frontmatter(content: str) -> Tuple[str, str]:
    """
    Splits the note content into frontmatter and body.
    Assumes frontmatter is delimited by '---' at the start and end.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---": return "", content
    frontmatter_lines: List[str] = [lines[0]]
    body_lines: List[str] = []
    in_frontmatter = True
    for i in range(1, len(lines)):
        line = lines[i]
        if in_frontmatter and line.strip() == "---":
            frontmatter_lines.append(line)
            in_frontmatter = False
            body_lines.extend(lines[i+1:])
            break
        elif in_frontmatter:
            frontmatter_lines.append(line)
        else: body_lines.append(line)
    if in_frontmatter: return "", content
    return "\n".join(frontmatter_lines), "\n".join(body_lines)

# --- Main Execution Block ---
if __name__ == "__main__":
    print("--- Starting Auto Linker Script (V2.3 - Simple Wikilinks) ---")
    obsidian: Optional[ObsidianPluginDevPythonToJS] = None

    try:
        obsidian = ObsidianPluginDevPythonToJS()
        print("INFO: Obsidian client initialized.")

        # --- Get Script Settings ---
        try:
            script_settings = obsidian.get_script_settings()
            link_type_preference = script_settings.get("link_type", MY_SCRIPT_SETTINGS[0]['default'])
            preserve_case_pref = script_settings.get("preserve_case", MY_SCRIPT_SETTINGS[1]['default'])
            ignore_accents_pref = script_settings.get("ignore_accents", MY_SCRIPT_SETTINGS[2]['default'])
            match_punctuation_pref = script_settings.get("match_punctuation", MY_SCRIPT_SETTINGS[3]['default'])
            print(f"INFO: Settings loaded: link_type='{link_type_preference}', preserve_case={preserve_case_pref}, ignore_accents={ignore_accents_pref}, match_punctuation={match_punctuation_pref}")
        except ObsidianCommError as e:
            print(f"ERROR: Could not get script settings: {e}. Using default linking options.", file=sys.stderr)
            link_type_preference = "wikilink"
            preserve_case_pref = True
            ignore_accents_pref = True
            match_punctuation_pref = True
            try: obsidian.show_notification(f"Error getting settings: {e}. Using defaults.", 5000)
            except: pass

        # --- Get Active Note Path ---
        try:
            note_path_abs = obsidian.get_active_note_absolute_path()
            print(f"INFO: Processing note: {note_path_abs}")
        except ObsidianCommError as e:
            print(f"ERROR: Could not get active note path: {e}", file=sys.stderr)
            try: obsidian.show_notification(f"Error: Active note path not found. {e}", 5000)
            except: pass
            sys.exit(1)

        # --- Get All Note Titles and Paths ---
        all_titles: Set[str] = set()
        title_to_rel_path: Dict[str, str] = {}
        try:
            relative_paths = obsidian.get_all_note_paths(absolute=False)
            print(f"INFO: Retrieved {len(relative_paths)} relative note paths.")
            if not relative_paths:
                 print("WARNING: No notes found in the vault. Cannot create links.", file=sys.stderr)
                 obsidian.show_notification("No notes found in vault.", 4000)
                 sys.exit(0)
            for rel_path in relative_paths:
                title = os.path.splitext(os.path.basename(rel_path))[0]
                if title:
                    all_titles.add(title)
                    title_to_rel_path[title] = rel_path
            print(f"INFO: Processed {len(all_titles)} unique note titles.")
            if not all_titles:
                 print("WARNING: No valid note titles found after processing.", file=sys.stderr)
                 obsidian.show_notification("No valid note titles found.", 4000)
                 sys.exit(0)
        except ObsidianCommError as e:
            print(f"ERROR: Could not get note paths/titles: {e}", file=sys.stderr)
            try: obsidian.show_notification(f"Error getting titles/paths: {e}", 5000)
            except: pass
            sys.exit(1)

        # --- Get Note Content ---
        try:
            original_content_union: Union[str, List[str]] = obsidian.get_active_note_content(return_format='string')
            if not isinstance(original_content_union, str):
                 if original_content_union is None: raise ObsidianCommError("Active note content received as None.")
                 else: raise ObsidianCommError(f"Expected string content, got {type(original_content_union).__name__}.")
            original_content = original_content_union
            print(f"INFO: Note content read ({len(original_content)} characters).")
        except ObsidianCommError as e:
            print(f"ERROR: Could not get note content: {e}", file=sys.stderr)
            try: obsidian.show_notification(f"Error reading content: {e}", 5000)
            except: pass
            sys.exit(1)

        # --- Process Content ---
        print("INFO: Splitting frontmatter and processing body for links...")
        frontmatter_str, body_str = split_frontmatter(original_content)
        # Use the updated linking function
        updated_body, content_changed = create_links_v3( # Use v3 function
            body_str,
            all_titles,
            title_to_rel_path,
            link_type_preference,
            preserve_case_pref,
            ignore_accents_pref,
            match_punctuation_pref
        )

        # Reconstruct final content
        if frontmatter_str and updated_body:
             if not frontmatter_str.endswith('\n'): frontmatter_str += '\n'
             final_content = frontmatter_str + updated_body
        elif frontmatter_str: final_content = frontmatter_str
        else: final_content = updated_body

        # --- Write Modified Content (if changed) ---
        if content_changed:
            print("INFO: Content modified, writing back via Obsidian API...")
            try:
                obsidian.modify_note_content(note_path_abs, final_content)
                print("INFO: Modification request sent successfully.")
                obsidian.show_notification(f"Auto-linking complete ({link_type_preference})!", 4000)
            except ObsidianCommError as e:
                print(f"ERROR: Failed to write note content: {e}", file=sys.stderr)
                try: obsidian.show_notification(f"Error saving changes: {e}", 5000)
                except: pass
                sys.exit(1)
        else:
            print("INFO: No changes made to the note content.")
            obsidian.show_notification("No new links created.", 3000)

        print("--- Auto Linker Script Finished ---")

    # --- General Error Handling ---
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        if obsidian:
            try: obsidian.show_notification(f"Bridge Error: {e}", 5000)
            except: pass
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected Python Error: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        if obsidian:
            try: obsidian.show_notification(f"Script Error: {e}", 5000)
            except: pass
        sys.exit(1)


