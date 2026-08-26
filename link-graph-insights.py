"""
Obsidian Python Bridge Script: Link Graph Insights (pure-Python PageRank)

POC: Google's original ranking algorithm, hand-rolled on your vault graph.
Builds the outgoing-link graph across all notes and computes:

- **PageRank** (damping 0.85, power iteration with dangling-mass redistribution)
- in/out degree centrality
- orphan notes (no links in either direction)

Then writes a dashboard note. No networkx, no numpy — ~90 lines of stdlib.

Requirements:
- Obsidian Python Bridge plugin v2.0.0+
- Python 3.x only.
"""

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
    {"key": "iterations", "type": "number", "label": "PageRank iterations", "default": 50},
    {"key": "top_n", "type": "number", "label": "Rows per table", "default": 10},
    {
        "key": "report_path",
        "type": "text",
        "label": "Report note path",
        "description": "Vault-relative path of the generated dashboard.",
        "default": "Link Graph Insights.md",
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()

DAMPING = 0.85


# --- Pure graph core ---


def normalise_targets(raw_links: list[str]) -> list[str]:
    """'folder/Sub Note.md' or 'Sub Note' -> 'Sub Note'."""
    out: set[str] = set()
    for link in raw_links:
        base = os.path.basename(link.replace("\\\\", "/"))
        title = os.path.splitext(base)[0]
        if title:
            out.add(title)
    return sorted(out)


def build_graph(titles: set[str], links_by_title: dict[str, list[str]]) -> dict[str, list[str]]:
    """Keep only edges pointing at known titles; drop self-loops & dupes."""
    graph: dict[str, list[str]] = {}
    for src in titles:
        targets = [t for t in links_by_title.get(src, []) if t in titles and t != src]
        graph[src] = sorted(set(targets))
    return graph


def pagerank(
    graph: dict[str, list[str]],
    damping: float = DAMPING,
    iterations: int = 50,
) -> dict[str, float]:
    """Classic PageRank power iteration with dangling-node redistribution."""
    nodes = list(graph.keys())
    n = len(nodes)
    if n == 0:
        return {}

    ranks = dict.fromkeys(nodes, 1.0 / n)
    out_degree = {node: len(graph[node]) for node in nodes}
    dangling = [node for node in nodes if out_degree[node] == 0]

    for _ in range(max(iterations, 1)):
        dangling_mass = sum(ranks[node] for node in dangling)
        new_ranks: dict[str, float] = {}
        for node in nodes:
            inbound = sum(
                ranks[other] / out_degree[other] for other in nodes if node in graph[other]
            )
            new_ranks[node] = (1 - damping) / n + damping * (inbound + dangling_mass / n)
        ranks = new_ranks

    total = sum(ranks.values()) or 1.0
    return {node: rank / total for node, rank in ranks.items()}


def degrees(graph: dict[str, list[str]]) -> tuple[dict[str, int], dict[str, int]]:
    """Return (out_degree, in_degree) mappings."""
    out_deg = {node: len(edges) for node, edges in graph.items()}
    in_deg = dict.fromkeys(graph, 0)
    for edges in graph.values():
        for target in edges:
            in_deg[target] += 1
    return out_deg, in_deg


def find_orphans(graph: dict[str, list[str]]) -> list[str]:
    out_deg, in_deg = degrees(graph)
    return sorted(n for n in graph if out_deg[n] == 0 and in_deg[n] == 0)


def top_rows(scores: dict[str, float], top_n: int) -> list[tuple[str, float]]:
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: max(top_n, 0)]
    return ranked


# --- Report rendering ---


def render_report(ranks: dict[str, float], graph: dict[str, list[str]], top_n: int) -> str:
    out_deg, in_deg = degrees(graph)
    lines: list[str] = ["# 🔗 Link Graph Insights", ""]

    lines += [
        "## Most important notes (PageRank)",
        "",
        "| Note | Score | In | Out |",
        "|---|---|---|---|",
    ]
    for name, score in top_rows(ranks, top_n):
        lines.append(f"| [[{name}]] | {score:.4f} | {in_deg[name]} | {out_deg[name]} |")

    lines += ["", "## Busiest out-links", "", "| Note | Out-degree |", "|---|---|"]
    for name, _ in top_rows({k: float(v) for k, v in out_deg.items()}, top_n):
        if out_deg[name] == 0:
            break
        lines.append(f"| [[{name}]] | {out_deg[name]} |")

    orphans = find_orphans(graph)
    lines += ["", f"## Orphan notes ({len(orphans)})", ""]
    lines += [f"- [[{name}]]" for name in orphans] if orphans else ["_None — fully connected!_"]
    lines.append("")
    return "\n".join(lines)


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    try:
        settings = obsidian.get_script_settings()
        iterations = int(settings.get("iterations", MY_SCRIPT_SETTINGS[0]["default"]))
        top_n = int(settings.get("top_n", MY_SCRIPT_SETTINGS[1]["default"]))
        report_path = str(settings.get("report_path", MY_SCRIPT_SETTINGS[2]["default"]))
    except ObsidianCommError:
        iterations, top_n, report_path = 50, 10, "Link Graph Insights.md"

    rel_paths = obsidian.get_all_note_paths(absolute=False)
    title_of = {rel: os.path.splitext(os.path.basename(rel))[0] for rel in rel_paths}
    titles = set(title_of.values())
    if not titles:
        obsidian.show_notification("Empty vault — nothing to analyse.", 4000)
        return

    links_by_title: dict[str, list[str]] = {}
    for rel, title in title_of.items():
        try:
            links_by_title[title] = normalise_targets(obsidian.get_links(rel, type="outgoing"))
        except ObsidianCommError as e:
            print(f"WARNING: links unavailable for '{rel}': {e}", file=sys.stderr)
            links_by_title[title] = []

    graph = build_graph(titles, links_by_title)
    ranks = pagerank(graph, iterations=iterations)

    report = render_report(ranks, graph, top_n)
    try:
        obsidian.create_note(report_path, report)
        obsidian.show_notification(f"Graph insights written to {report_path}", 5000)
    except ObsidianCommError as e:
        print(f"ERROR: could not write report: {e}", file=sys.stderr)
        obsidian.show_notification(f"Failed to write report: {e}", 6000)


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
