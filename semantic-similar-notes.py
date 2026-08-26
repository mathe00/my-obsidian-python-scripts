"""
Obsidian Python Bridge Script: Semantic Similar Notes (zero-dependency NLP)

POC showcasing why Python is fun: a mini TF-IDF + cosine-similarity engine
written entirely with the standard library (math, collections, re). It reads
every note in the vault, vectorises the bodies, and suggests notes related to
the active one that are NOT yet linked — surfacing "missing links".

No scikit-learn, no numpy: just dictionaries and trigonometry. That is the
whole point — this is ~120 lines of Python and would be a genuinely annoying
weekend project in TypeScript.

Structure follows the recommended bridge boilerplate; orchestration lives in
an injectable ``run(client)`` for testing.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x only — NO third-party packages needed.
"""

import os
import re
import sys
import unicodedata
from collections import Counter
from math import log, sqrt

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

# --- Event helper (modern API first, graceful fallback) ---
try:
    from ObsidianPluginDevPythonToJS import is_handling_event
except ImportError:

    def is_handling_event() -> bool:  # type: ignore[misc]
        return bool(os.environ.get("OBSIDIAN_EVENT_NAME"))


if is_handling_event():
    sys.exit(0)

MY_SCRIPT_SETTINGS = [
    {
        "key": "top_k",
        "type": "number",
        "label": "Max suggestions",
        "description": "How many related notes to suggest.",
        "default": 5,
    },
    {
        "key": "min_score",
        "type": "number",
        "label": "Minimum similarity",
        "description": "Cosine similarity threshold (0-1). Higher = stricter.",
        "default": 0.08,
    },
    {
        "key": "append_section",
        "type": "toggle",
        "label": "Append 'Related notes' section to active note",
        "description": "If disabled, results are shown only in a notification.",
        "default": True,
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()

SECTION_START = "<!-- semantic-related:start -->"
SECTION_END = "<!-- semantic-related:end -->"

_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
    ]
)

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


# --- Pure NLP core (no bridge dependency) ---


def tokenize(text: str) -> list[str]:
    """Lowercase, strip accents/diacritics, drop stopwords & short tokens."""
    text = "".join(
        c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn"
    )
    return [t for t in _TOKEN_RE.findall(text) if t not in _STOPWORDS]


def build_tfidf(documents: dict[str, str]) -> dict[str, dict[str, float]]:
    """Return L2-normalised TF-IDF vectors keyed by document name."""
    tokenised = {name: tokenize(body) for name, body in documents.items()}
    n_docs = len(tokenised) or 1

    doc_freq: Counter[str] = Counter()
    for tokens in tokenised.values():
        doc_freq.update(set(tokens))

    vectors: dict[str, dict[str, float]] = {}
    for name, tokens in tokenised.items():
        if not tokens:
            vectors[name] = {}
            continue
        counts = Counter(tokens)
        total = len(tokens)
        vec = {
            term: (count / total) * (log((1 + n_docs) / (1 + doc_freq[term])) + 1.0)
            for term, count in counts.items()
        }
        norm = sqrt(sum(w * w for w in vec.values())) or 1.0
        vectors[name] = {term: w / norm for term, w in vec.items()}
    return vectors


def cosine(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Cosine similarity between two sparse L2-normalised vectors."""
    if len(vec_b) < len(vec_a):
        vec_a, vec_b = vec_b, vec_a
    return sum(w * vec_b.get(term, 0.0) for term, w in vec_a.items())


def suggest_related(
    active_name: str,
    vectors: dict[str, dict[str, float]],
    already_linked: set[str],
    top_k: int,
    min_score: float,
) -> list[tuple[str, float]]:
    """Rank other documents by similarity to *active_name*, skipping links."""
    active_vec = vectors.get(active_name, {})
    scored = [
        (name, round(cosine(active_vec, vec), 4))
        for name, vec in vectors.items()
        if name != active_name and name not in already_linked
    ]
    scored = [(name, score) for name, score in scored if score >= min_score]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[: max(top_k, 0)]


def render_section(suggestions: list[tuple[str, float]]) -> str:
    """Render the idempotent markdown block inserted into the note."""
    lines = [SECTION_START, "", "**Related notes (TF-IDF):**", ""]
    if suggestions:
        lines += [f"- [[{name}]] _(similarity {score:.3f})_" for name, score in suggestions]
    else:
        lines.append("_No related notes found above threshold._")
    lines += ["", SECTION_END, ""]
    return "\n".join(lines)


def upsert_section(content: str, new_section: str) -> str:
    """Insert *new_section*, replacing any previously generated one."""
    pattern = re.compile(re.escape(SECTION_START) + r".*?" + re.escape(SECTION_END), re.DOTALL)
    if pattern.search(content):
        return pattern.sub(new_section.rstrip("\n"), content)
    return content.rstrip("\n") + "\n\n" + new_section


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    try:
        settings = obsidian.get_script_settings()
        top_k = int(settings.get("top_k", MY_SCRIPT_SETTINGS[0]["default"]))
        min_score = float(settings.get("min_score", MY_SCRIPT_SETTINGS[1]["default"]))
        append_section = bool(settings.get("append_section", MY_SCRIPT_SETTINGS[2]["default"]))
    except ObsidianCommError:
        top_k, min_score, append_section = 5, 0.08, True

    active_rel = obsidian.get_active_note_relative_path()
    active_title = os.path.splitext(os.path.basename(active_rel))[0]

    all_paths = obsidian.get_all_note_paths(absolute=False)
    if len(all_paths) < 2:
        obsidian.show_notification("Not enough notes to compare.", 4000)
        return

    documents: dict[str, str] = {}
    for rel_path in all_paths:
        title = os.path.splitext(os.path.basename(rel_path))[0]
        try:
            documents[title] = obsidian.get_note_content(rel_path) or ""
        except ObsidianCommError as e:
            print(f"WARNING: skipping '{rel_path}': {e}", file=sys.stderr)

    outgoing: set[str] = set()
    try:
        raw_links = obsidian.get_links(active_rel, type="outgoing")
        outgoing = {
            os.path.splitext(os.path.basename(link))[0]
            if "/" in link
            else os.path.splitext(link)[0]
            for link in raw_links
        }
    except ObsidianCommError as e:
        print(f"WARNING: could not fetch outgoing links: {e}", file=sys.stderr)

    vectors = build_tfidf(documents)
    suggestions = suggest_related(active_title, vectors, outgoing, top_k, min_score)

    summary = ", ".join(name for name, _ in suggestions) or "none"
    obsidian.show_notification(f"Related: {summary}", 6000)

    if append_section:
        content = obsidian.get_active_note_content(return_format="string") or ""
        updated = upsert_section(content, render_section(suggestions))
        abs_path = obsidian.get_active_note_absolute_path()
        obsidian.modify_note_content(abs_path, updated)


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
