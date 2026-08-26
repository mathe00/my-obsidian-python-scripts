"""
Obsidian Python Bridge Script: Vault Analytics (data-science flex)

POC of Python's data stack on your vault:

- **With pandas (+matplotlib)** installed: real DataFrame statistics and a
  PNG word-count histogram embedded into the dashboard note.
- **Without**: identical report, computed in pure stdlib — the script
  degrades gracefully instead of failing.

Either way you get a generated dashboard note: total notes/words, mean,
median, longest-notes leaderboard, and the chart when available.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Optional: ``pip install pandas matplotlib`` for the full experience.
"""

import os
import statistics
import sys
from typing import Any

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

# --- Optional heavy deps: the entire point is graceful degradation ---
try:
    import pandas as pd  # type: ignore

    HAS_PANDAS = True
except ImportError:
    pd = None  # type: ignore[assignment]
    HAS_PANDAS = False

try:
    import matplotlib

    matplotlib.use("Agg")  # headless — we only save PNGs
    import matplotlib.pyplot as plt  # type: ignore

    HAS_MPL = True
except ImportError:
    plt = None  # type: ignore[assignment]
    HAS_MPL = False


MY_SCRIPT_SETTINGS = [
    {"key": "top_n", "type": "number", "label": "Leaderboard size", "default": 10},
    {
        "key": "create_chart",
        "type": "toggle",
        "label": "Generate PNG histogram",
        "description": "Requires matplotlib. Silently skipped otherwise.",
        "default": True,
    },
    {
        "key": "report_path",
        "type": "text",
        "label": "Dashboard note path",
        "default": "Vault Analytics.md",
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()


# --- Pure core ---


def compute_metrics(documents: dict[str, str]) -> list[dict[str, Any]]:
    """Per-note word/char counts, sorted by word count desc."""
    rows = [
        {"title": title, "words": len(body.split()), "chars": len(body)}
        for title, body in documents.items()
    ]
    rows.sort(key=lambda r: r["words"], reverse=True)
    return rows


def summarise(word_counts: list[int]) -> dict[str, float]:
    """Stdlib descriptive stats over non-empty counts."""
    if not word_counts:
        return {}
    return {
        "notes": len(word_counts),
        "total_words": sum(word_counts),
        "mean": round(statistics.fmean(word_counts), 1),
        "median": round(statistics.median(word_counts), 1),
        "max": max(word_counts),
    }


def render_report(
    metrics: list[dict[str, Any]],
    summary: dict[str, float],
    top_n: int,
    chart_filename: str | None,
    engine: str,
) -> str:
    lines: list[str] = ["# 📊 Vault Analytics", "", f"_Engine: {engine}_", "", "## Summary", ""]
    if summary:
        lines += [
            f"- Notes analysed: **{summary['notes']}**",
            f"- Total words: **{summary['total_words']:,}**",
            f"- Mean words/note: **{summary['mean']}** · median **{summary['median']}** · max **{summary['max']:,}**",
        ]
    else:
        lines.append("_No notes found._")

    if chart_filename:
        lines += ["", f"![Word count histogram]({chart_filename})"]

    lines += ["", f"## Top {top_n} longest notes", "", "| Note | Words | Chars |", "|---|---|---|"]
    for row in metrics[: max(top_n, 0)]:
        lines.append(f"| [[{row['title']}]] | {row['words']:,} | {row['chars']:,} |")
    lines.append("")
    return "\n".join(lines)


def build_histogram_png(word_counts: list[int], png_path: str) -> bool:
    """Save a histogram PNG; False when matplotlib is unavailable."""
    if not HAS_MPL or not word_counts:
        return False
    plt.figure(figsize=(8, 4))
    plt.hist(word_counts, bins=30, color="#7c3aed", edgecolor="white")
    plt.title("Words per note")
    plt.xlabel("Words")
    plt.ylabel("Notes")
    plt.tight_layout()
    plt.savefig(png_path, dpi=120)
    plt.close()
    return True


def pick_engine(create_chart_requested: bool) -> tuple[str, bool]:
    """Return (engine_label, chart_possible)."""
    if HAS_PANDAS and HAS_MPL:
        return "pandas + matplotlib", create_chart_requested
    if HAS_PANDAS:
        return "pandas (no matplotlib)", False
    return "pure stdlib fallback", False


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    try:
        settings = obsidian.get_script_settings()
        top_n = int(settings.get("top_n", MY_SCRIPT_SETTINGS[0]["default"]))
        want_chart = bool(settings.get("create_chart", MY_SCRIPT_SETTINGS[1]["default"]))
        report_path = str(settings.get("report_path", MY_SCRIPT_SETTINGS[2]["default"]))
    except ObsidianCommError:
        top_n, want_chart, report_path = 10, True, "Vault Analytics.md"

    rel_paths = obsidian.get_all_note_paths(absolute=False)
    documents: dict[str, str] = {}
    for rel in rel_paths:
        title = os.path.splitext(os.path.basename(rel))[0]
        try:
            documents[title] = obsidian.get_note_content(rel) or ""
        except ObsidianCommError as e:
            print(f"WARNING: skipping '{rel}': {e}", file=sys.stderr)

    if not documents:
        obsidian.show_notification("Empty vault — nothing to analyse.", 4000)
        return

    # Optional pandas pass (kept tiny: the DataFrame IS the demo).
    global_summary: dict[str, float] = {}
    if HAS_PANDAS:
        frame = pd.DataFrame(compute_metrics(documents))
        global_summary["mean"] = round(float(frame["words"].mean()), 1)
        global_summary["std"] = round(float(frame["words"].std(ddof=0)), 1)

    metrics = compute_metrics(documents)
    base_summary = summarise([m["words"] for m in metrics])
    base_summary.update(global_summary)

    engine, chart_possible = pick_engine(want_chart)

    chart_filename: str | None = None
    if chart_possible:
        png_abs = os.path.splitext(report_path)[0] + ".png"
        if build_histogram_png([m["words"] for m in metrics], png_abs):
            chart_filename = os.path.basename(png_abs)

    report = render_report(metrics, base_summary, top_n, chart_filename, engine)
    try:
        obsidian.create_note(report_path, report)
        obsidian.show_notification(f"Analytics ready ({engine}) → {report_path}", 5000)
    except ObsidianCommError as e:
        print(f"ERROR: could not write dashboard: {e}", file=sys.stderr)
        obsidian.show_notification(f"Failed: {e}", 6000)


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
