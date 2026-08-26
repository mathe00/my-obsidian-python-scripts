"""Unit tests for link-graph-insights.py (pure-Python PageRank)."""

from typing import ClassVar

import pytest
from conftest import load_script

mod = load_script("link-graph-insights.py")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class TestNormaliseTargets:
    def test_paths_titles_and_dupes(self):
        raw = ["folder/Sub Note.md", "Sub Note", "Other.md", ""]
        assert mod.normalise_targets(raw) == ["Other", "Sub Note"]


class TestBuildGraph:
    def test_filters_unknown_targets_and_selfloops(self):
        graph = mod.build_graph({"A", "B"}, {"A": ["B", "Ghost", "A"], "B": []})
        assert graph == {"A": ["B"], "B": []}


# ---------------------------------------------------------------------------
# pagerank
# ---------------------------------------------------------------------------


class TestPageRank:
    def test_empty_graph(self):
        assert mod.pagerank({}) == {}

    def test_ranks_sum_to_one(self):
        graph = {"A": ["B"], "B": ["A"], "C": []}
        ranks = mod.pagerank(graph)
        assert sum(ranks.values()) == pytest.approx(1.0)

    def test_mutual_pair_symmetric(self):
        ranks = mod.pagerank({"A": ["B"], "B": ["A"]})
        assert ranks["A"] == pytest.approx(ranks["B"])

    def test_hub_ranks_higher_than_leaf(self):
        # C is pointed at by both A and B; A and B point only at C.
        graph = {
            "A": ["C"],
            "B": ["C"],
            "C": [],
        }
        ranks = mod.pagerank(graph)
        assert ranks["C"] > ranks["A"]
        assert ranks["C"] > ranks["B"]

    def test_dangling_mass_redistributed(self):
        # Single dangling node must keep total probability mass at 1.
        ranks = mod.pagerank({"Loner": []})
        assert sum(ranks.values()) == pytest.approx(1.0)
        assert ranks["Loner"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# degrees & orphans
# ---------------------------------------------------------------------------


class TestDegreesOrphans:
    GRAPH: ClassVar[dict] = {"A": ["B", "C"], "B": ["C"], "C": [], "Island": []}

    def test_degrees(self):
        out_deg, in_deg = mod.degrees(self.GRAPH)
        assert out_deg["A"] == 2
        assert in_deg["C"] == 2
        assert in_deg["A"] == 0

    def test_orphans(self):
        assert mod.find_orphans(self.GRAPH) == ["Island"]

    def test_top_rows_sorted_truncated(self):
        rows = mod.top_rows({"a": 0.2, "b": 0.5, "c": 0.3}, top_n=2)
        assert rows == [("b", 0.5), ("c", 0.3)]


# ---------------------------------------------------------------------------
# report rendering
# ---------------------------------------------------------------------------


class TestRenderReport:
    def test_contains_tables_and_orphans(self):
        graph = {"A": ["B"], "B": [], "Alone": []}
        ranks = mod.pagerank(graph)
        report = mod.render_report(ranks, graph, top_n=5)
        assert "| [[A]] |" in report or "| [[B]] |" in report
        assert "- [[Alone]]" in report


# ---------------------------------------------------------------------------
# run() with fake bridge
# ---------------------------------------------------------------------------


@pytest.fixture()
def graph_bridge(bind_client, fake_bridge):
    fake_bridge.get_all_note_paths.return_value = ["A.md", "B.md", "Alone.md"]
    fake_bridge.get_links.side_effect = lambda p, type="outgoing": {
        "A.md": ["[[B]]"],
        "B.md": [],
        "Alone.md": [],
    }[p]
    return fake_bridge


class TestRun:
    def test_report_created_with_expected_sections(self, graph_bridge):
        mod.run(graph_bridge)

        args, _ = graph_bridge.create_note.call_args
        path, content = args[0], args[1]
        assert path.endswith("Link Graph Insights.md")
        assert "## Most important notes (PageRank)" in content
        assert "- [[Alone]]" in content

    def test_empty_vault_short_circuits(self, bind_client, fake_bridge):
        bind_client(mod)
        fake_bridge.get_all_note_paths.return_value = []

        mod.run(fake_bridge)

        fake_bridge.create_note.assert_not_called()
