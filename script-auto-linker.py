"""
Obsidian Python Bridge Script: Auto Linker (V2.4 - Robust Matching)

This script automatically creates links in the currently active note.
It searches for text matching the titles (case-insensitive, accent-insensitive)
of other notes in the vault and converts them into one of three types based on
settings:
- Wikilink with Alias: [[Note Title|Matched Text]]
- Simple Wikilink:     [[Note Title]]
- Markdown Link:       [Matched Text](Note%20Path.md)

Features:
- Preserves existing YAML frontmatter.
- Avoids creating links inside existing Markdown links, wikilinks, or code blocks.
- Configurable link type via Plugin Settings.
- Configurable case preservation (Alias/Markdown), accent ignorance, punctuation handling.
- Handles multi-word titles correctly, even mid-sentence with different casing/accents.
- Uses a find-all-then-replace strategy for robustness.

Pure logic lives in testable functions; :func:`run` holds the bridge
orchestration and accepts an injectable client for testing.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x
- 'requests' library (`pip install requests`)
"""

import os
import re
import sys
import unicodedata
import urllib.parse
from typing import NamedTuple

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

# --- Settings Definition & Discovery Handling ---
MY_SCRIPT_SETTINGS = [
    {
        "key": "link_type",
        "type": "dropdown",
        "label": "Link Type",
        "description": "Choose the format for created links.",
        "default": "wikilink",  # Default to piped wikilink
        "options": ["wikilink", "simple_wikilink", "markdown"],
    },
    {
        "key": "preserve_case",
        "type": "toggle",
        "label": "Preserve Original Case (for Alias/Markdown)",
        "description": (
            "If enabled, link text keeps original casing "
            "(e.g., [[Title|oRiginal]] or [oRiginal](...). Ignored for Simple Wikilinks."
        ),
        "default": True,
    },
    {
        "key": "ignore_accents",
        "type": "toggle",
        "label": "Ignore Accents When Matching",
        "description": "If enabled, 'cafe' in your text can link to a note titled 'Café'.",
        "default": True,
    },
    {
        "key": "match_punctuation",
        "type": "toggle",
        "label": "Match Adjacent Punctuation",
        "description": (
            "If enabled, attempts to include punctuation like '.' or ',' immediately "
            "following the matched text outside the link."
        ),
        "default": True,
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()  # Handles --get-settings-json and exits if present


# --- Core Logic Functions (pure) ---


def remove_accents(text: str) -> str:
    """Normalize *text* by removing diacritics ('Café' -> 'Cafe')."""
    if not isinstance(text, str):
        return text
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def is_inside_link_or_code(index: int, content: str) -> bool:
    """Check whether *index* sits inside a known link/code structure.

    Simplified heuristic checks for ``[[...]]``, ``[...](...)``, inline
    ```code` `` and fenced ``` ``` ``` blocks. May produce rare false
    positives (e.g. stray parentheses); accepted trade-off documented in the
    README.
    """
    # Check [[...]]
    link_start = content.rfind("[[", 0, index)
    link_end = content.find("]]", index)
    if -1 < link_start < index < link_end:
        return True
    # Check [...](...)
    paren_start = content.rfind("(", 0, index)
    paren_end = content.find(")", index)
    if -1 < paren_start < index < paren_end:
        bracket_end = content.rfind("]", 0, paren_start)
        if -1 < bracket_end < paren_start:
            return True
    # Check `...`
    if content[:index].count("`") % 2 != 0:
        next_backtick = content.find("`", index)
        if next_backtick != -1:
            return True
    # Check ```...```
    block_start = content.rfind("```", 0, index)
    if block_start != -1:
        block_end = content.find("```", block_start + 3)
        if block_end == -1 or index < block_end:
            return True
    return False


class MatchInfo(NamedTuple):
    """A candidate match found in the document body."""

    start: int
    end: int
    title: str  # Canonical title (original accents/case)
    matched_text: str  # Text found in the document (original accents/case)
    trailing_char: str  # Character(s) immediately following the match


def create_links_v3(
    original_body: str,
    titles_set: set[str],
    title_to_path_map: dict[str, str],
    link_type_pref: str,
    preserve_case: bool,
    ignore_accents: bool,
    match_punctuation: bool,
) -> tuple[str, bool]:
    """Convert text matching vault note titles into links.

    Find-all-then-replace strategy: collect every candidate match, sort by
    position (longest first on ties), drop overlaps and matches inside
    existing links/code, then rebuild the string segment by segment.

    Args:
        original_body: The main body content of the note (frontmatter excluded).
        titles_set: All unique note titles in the vault.
        title_to_path_map: Mapping from note title to its relative path.
        link_type_pref: "wikilink", "simple_wikilink" or "markdown".
        preserve_case: Keep original casing in the alias/text when True.
        ignore_accents: Ignore accents during matching when True.
        match_punctuation: Include adjacent punctuation as trailing char.

    Returns:
        ``(processed_content, content_was_changed)``.
    """
    if not original_body or not titles_set:
        return original_body, False

    search_body = remove_accents(original_body) if ignore_accents else original_body
    all_matches: list[MatchInfo] = []

    # 1. Find all potential matches — longest titles first so that longer
    #    candidates win over their prefixes at equal start positions.
    sorted_titles = sorted(titles_set, key=len, reverse=True)
    for title in sorted_titles:
        if not title:
            continue

        normalized_title = remove_accents(title) if ignore_accents else title
        escaped_title = re.escape(normalized_title)

        trailing_char_pattern = r"([\s.,;!?()]|$)" if match_punctuation else r"(\s|$|\b)"
        regex_pattern = rf"\b({escaped_title}){trailing_char_pattern}"
        regex = re.compile(regex_pattern, re.IGNORECASE)

        for match in regex.finditer(search_body):
            start_idx, end_idx = match.span()
            title_end_idx = start_idx + len(match.group(1))
            original_matched_text = original_body[start_idx:title_end_idx]
            original_trailing_char = original_body[title_end_idx:end_idx]

            all_matches.append(
                MatchInfo(
                    start=start_idx,
                    end=end_idx,
                    title=title,
                    matched_text=original_matched_text,
                    trailing_char=original_trailing_char,
                )
            )

    # 2. Filter and select valid, non-overlapping matches.
    if not all_matches:
        return original_body, False
    all_matches.sort(key=lambda m: (m.start, -len(m.matched_text)))

    valid_matches: list[MatchInfo] = []
    last_processed_end_index = -1

    for match in all_matches:
        if match.start < last_processed_end_index:
            continue  # Overlaps a previously kept match — skip.
        check_index = match.start + len(match.matched_text) // 2
        if is_inside_link_or_code(check_index, original_body):
            continue  # Already inside an existing link/code structure.
        valid_matches.append(match)
        last_processed_end_index = match.end

    # 3. Build the new string using valid matches.
    if not valid_matches:
        return original_body, False

    new_content_parts: list[str] = []
    current_index = 0
    content_changed = False

    for match in valid_matches:
        new_content_parts.append(original_body[current_index : match.start])

        link_text = match.matched_text if preserve_case else match.title
        link_target = match.title  # Canonical title used as target.

        if link_type_pref == "markdown":
            relative_path = title_to_path_map.get(match.title)
            if relative_path:
                encoded_path = urllib.parse.quote(relative_path)
                link_string = f"[{link_text}]({encoded_path})"
            else:
                print(
                    f"WARNING: Path not found for title '{match.title}' for Markdown link.",
                    file=sys.stderr,
                )
                link_string = match.matched_text  # Fallback: leave text untouched.
        elif link_type_pref == "simple_wikilink":
            link_string = f"[[{link_target}]]"
        else:  # Default to piped wikilink
            link_string = f"[[{link_target}|{link_text}]]"

        new_content_parts.append(link_string)
        new_content_parts.append(match.trailing_char)

        current_index = match.end
        content_changed = True

    new_content_parts.append(original_body[current_index:])
    return "".join(new_content_parts), content_changed


def split_frontmatter(content: str) -> tuple[str, str]:
    """Split *content* into ``(frontmatter_block, body)``.

    Assumes frontmatter is delimited by ``---`` as first line and a closing
    ``---`` line. If no valid frontmatter exists, returns ``("", content)``
    unchanged.
    """
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", content
    frontmatter_lines: list[str] = [lines[0]]
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            # Closing delimiter found: everything after belongs to the body.
            frontmatter_lines.append(line)
            return "\n".join(frontmatter_lines), "\n".join(lines[i + 1 :])
        frontmatter_lines.append(line)
    # Closing delimiter never found -> not valid frontmatter, return unchanged.
    return "", content


def reconstruct(frontmatter_str: str, updated_body: str) -> str:
    """Rejoin frontmatter and body with a newline separation guarantee."""
    if frontmatter_str and updated_body:
        if not frontmatter_str.endswith("\n"):
            frontmatter_str += "\n"
        return frontmatter_str + updated_body
    if frontmatter_str:
        return frontmatter_str
    return updated_body


# --- Orchestration (bridge-dependent, injectable for tests) ---
def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    """Run auto-linking on the currently active note using *obsidian*."""
    # --- Get Script Settings ---
    try:
        script_settings = obsidian.get_script_settings()
        link_type_preference = script_settings.get("link_type", MY_SCRIPT_SETTINGS[0]["default"])
        preserve_case_pref = script_settings.get("preserve_case", MY_SCRIPT_SETTINGS[1]["default"])
        ignore_accents_pref = script_settings.get(
            "ignore_accents", MY_SCRIPT_SETTINGS[2]["default"]
        )
        match_punctuation_pref = script_settings.get(
            "match_punctuation", MY_SCRIPT_SETTINGS[3]["default"]
        )
        print(
            f"INFO: Settings loaded: link_type='{link_type_preference}', "
            f"preserve_case={preserve_case_pref}, ignore_accents={ignore_accents_pref}, "
            f"match_punctuation={match_punctuation_pref}"
        )
    except ObsidianCommError as e:
        print(
            f"ERROR: Could not get script settings: {e}. Using default linking options.",
            file=sys.stderr,
        )
        link_type_preference = "wikilink"
        preserve_case_pref = True
        ignore_accents_pref = True
        match_punctuation_pref = True
        try:
            obsidian.show_notification(f"Error getting settings: {e}. Using defaults.", 5000)
        except Exception:
            pass

    # --- Get Active Note Path ---
    try:
        note_path_abs = obsidian.get_active_note_absolute_path()
        print(f"INFO: Processing note: {note_path_abs}")
    except ObsidianCommError as e:
        print(f"ERROR: Could not get active note path: {e}", file=sys.stderr)
        try:
            obsidian.show_notification(f"Error: Active note path not found. {e}", 5000)
        except Exception:
            pass
        sys.exit(1)

    # --- Get All Note Titles and Paths ---
    all_titles: set[str] = set()
    title_to_rel_path: dict[str, str] = {}
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
        try:
            obsidian.show_notification(f"Error getting titles/paths: {e}", 5000)
        except Exception:
            pass
        sys.exit(1)

    # --- Get Note Content ---
    try:
        original_content = obsidian.get_active_note_content(return_format="string")
        if original_content is None:
            raise ObsidianCommError("Active note content received as None.")
        if not isinstance(original_content, str):
            raise ObsidianCommError(
                f"Expected string content, got {type(original_content).__name__}."
            )
        print(f"INFO: Note content read ({len(original_content)} characters).")
    except ObsidianCommError as e:
        print(f"ERROR: Could not get note content: {e}", file=sys.stderr)
        try:
            obsidian.show_notification(f"Error reading content: {e}", 5000)
        except Exception:
            pass
        sys.exit(1)

    # --- Process Content ---
    print("INFO: Splitting frontmatter and processing body for links...")
    frontmatter_str, body_str = split_frontmatter(original_content)
    updated_body, content_changed = create_links_v3(
        body_str,
        all_titles,
        title_to_rel_path,
        link_type_preference,
        preserve_case_pref,
        ignore_accents_pref,
        match_punctuation_pref,
    )

    final_content = reconstruct(frontmatter_str, updated_body)

    # --- Write Modified Content (if changed) ---
    if content_changed:
        print("INFO: Content modified, writing back via Obsidian API...")
        try:
            obsidian.modify_note_content(note_path_abs, final_content)
            print("INFO: Modification request sent successfully.")
            obsidian.show_notification(f"Auto-linking complete ({link_type_preference})!", 4000)
        except ObsidianCommError as e:
            print(f"ERROR: Failed to write note content: {e}", file=sys.stderr)
            try:
                obsidian.show_notification(f"Error saving changes: {e}", 5000)
            except Exception:
                pass
            sys.exit(1)
    else:
        print("INFO: No changes made to the note content.")
        obsidian.show_notification("No new links created.", 3000)


# --- Main Execution Block ---
if __name__ == "__main__":
    print("--- Starting Auto Linker Script (V2.4 - Robust Matching) ---")
    try:
        obsidian = ObsidianPluginDevPythonToJS()
        print("INFO: Obsidian client initialized.")
        run(obsidian)
        print("--- Auto Linker Script Finished ---")

    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected Python Error: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
