"""
Obsidian Python Bridge Script: Fuzzy Duplicate Finder (stdlib difflib)

POC: mine the vault for near-duplicate notes without any fuzzy-matching
library. Titles are compared pairwise with ``difflib.SequenceMatcher``
(the same engine powering Python's own diff tooling); exact body duplicates
are caught with MD5 fingerprints of normalised content.

O(n²) on titles — perfectly fine for personal vaults, documented honestly.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x only.
"""

import hashlib
import os
import re
import sys
from difflib import SequenceMatcher

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
        "key": "title_threshold",
        "type": "number",
        "label": "Title similarity threshold (0-1)",
        "description": "Pairs scoring above this ratio are reported.",
        "default": 0.85,
    },
    {
        "key": "detect_body_duplicates",
        "type": "toggle",
        "label": "Also detect exact body duplicates (MD5)",
        "default": True,
    },
    {
        "key": "create_report",
        "type": "toggle",
        "label": "Write a report note",
        "description": "Otherwise findings go to a notification only.",
        "default": True,
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()

REPORT_PATH = "Fuzzy Duplicates Report.md"
_WS_RE = re.compile(r"\s+")


# --- Pure core ---


def normalise_title(title: str) -> str:
    """Casefold + squeeze whitespace so 'My Note' == 'my   note'."""
    return _WS_RE.sub(" ", title.casefold()).strip()


def similar_title_pairs(
    titles: list[str],
    threshold: float = 0.85,
) -> list[tuple[str, str, float]]:
    """All pairs whose normalised titles score above *threshold* (sorted desc)."""
    norm_map = {t: normalise_title(t) for t in titles}
    pairs: list[tuple[str, str, float]] = []
    seen_pairs: set[tuple[str, str]] = set()

    items = list(norm_map.items())
    for i, (title_a, norm_a) in enumerate(items):
        for title_b, norm_b in items[i + 1 :]:
            score = 1.0 if norm_a == norm_b else SequenceMatcher(None, norm_a, norm_b).ratio()
            if score >= threshold:
                key = tuple(sorted((norm_a, norm_b)))
                if key not in seen_pairs:
                    seen_pairs.add(key)
                    pairs.append((title_a, title_b, round(score, 3)))

    pairs.sort(key=lambda p: p[2], reverse=True)
    return pairs


def body_fingerprint(content: str) -> str:
    """MD5 of casefolded whitespace-collapsed content (frontmatter excluded upstream)."""
    normalised = _WS_RE.sub(" ", content.casefold()).strip()
    return hashlib.md5(normalised.encode("utf-8")).hexdigest()


def exact_body_groups(contents: dict[str, str]) -> list[list[str]]:
    """Group titles sharing identical normalised bodies (groups of size > 1)."""
    buckets: dict[str, list[str]] = {}
    for title, body in contents.items():
        buckets.setdefault(body_fingerprint(body), []).append(title)
    return [sorted(group) for group in buckets.values() if len(group) > 1]


def render_report(title_pairs: list[tuple[str, str, float]], groups: list[list[str]]) -> str:
    lines: list[str] = ["# 🔍 Fuzzy Duplicates Report", ""]

    lines += [f"## Similar titles ({len(title_pairs)})", ""]
    lines += (
        [f"- {score:.0%} — [[{a}]] ↔ [[{b}]]" for a, b, score in title_pairs]
        if title_pairs
        else ["_None found._"]
    )

    lines += ["", f"## Identical bodies ({len(groups)} group(s))", ""]
    if groups:
        for group in groups:
            members = ", ".join(f"[[{t}]]" for t in group)
            lines.append(f"- {members}")
    else:
        lines.append("_None found._")

    lines.append("")
    return "\n".join(lines)


def summarise_notification(title_pairs: list, groups: list) -> str:
    total = len(title_pairs) + len(groups)
    if total == 0:
        return "No duplicate suspects found. Vault is clean ✨"
    return f"{len(title_pairs)} similar title(s), {len(groups)} identical body group(s)"


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    try:
        settings = obsidian.get_script_settings()
        threshold = float(settings.get("title_threshold", MY_SCRIPT_SETTINGS[0]["default"]))
        check_bodies = bool(
            settings.get("detect_body_duplicates", MY_SCRIPT_SETTINGS[1]["default"])
        )
        create_report = bool(settings.get("create_report", MY_SCRIPT_SETTINGS[2]["default"]))
    except ObsidianCommError:
        threshold, check_bodies, create_report = 0.85, True, True

    rel_paths = obsidian.get_all_note_paths(absolute=False)
    titles = [os.path.splitext(os.path.basename(p))[0] for p in rel_paths]
    if len(titles) < 2:
        obsidian.show_notification("Not enough notes to compare.", 4000)
        return

    title_pairs = similar_title_pairs(titles, threshold)

    groups: list[list[str]] = []
    if check_bodies:
        contents: dict[str, str] = {}
        for rel in rel_paths:
            try:
                contents[os.path.splitext(os.path.basename(rel))[0]] = (
                    obsidian.get_note_content(rel) or ""
                )
            except ObsidianCommError as e:
                print(f"WARNING: cannot read '{rel}': {e}", file=sys.stderr)
        groups = exact_body_groups(contents)

    obsidian.show_notification(summarise_notification(title_pairs, groups), 5000)

    if create_report:
        obsidian.create_note(REPORT_PATH, render_report(title_pairs, groups))


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
