"""Unit tests for vault-analytics.py (stdlib path — heavy deps never imported)."""

import pytest
from conftest import load_script

mod = load_script("vault-analytics.py")


DOCS = {
    "Short": "three words only",
    "Long": " ".join(["word"] * 100),
    "Medium": "a b c d e f g h i j",  # 10 words
}


# ---------------------------------------------------------------------------
# metrics & stats
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_counts_and_sorting(self):
        rows = mod.compute_metrics(DOCS)
        assert [r["title"] for r in rows] == ["Long", "Medium", "Short"]
        # 'word ' x100 -> 400 letters + 99 joining spaces.
        assert rows[0]["words"] == 100 and rows[0]["chars"] == 499

    def test_empty_body(self):
        rows = mod.compute_metrics({"Blank": ""})
        assert rows == [{"title": "Blank", "words": 0, "chars": 0}]


class TestSummarise:
    def test_known_values(self):
        s = mod.summarise([10, 20, 30, 40])
        assert s["notes"] == 4
        assert s["total_words"] == 100
        assert s["mean"] == 25.0
        assert s["median"] == 25.0
        assert s["max"] == 40

    def test_empty_input(self):
        assert mod.summarise([]) == {}

    def test_even_count_median_average(self):
        assert mod.summarise([1, 3])["median"] == 2.0


# ---------------------------------------------------------------------------
# report rendering (stdlib engine, optional chart line)
# ---------------------------------------------------------------------------


class TestRenderReport:
    METRICS = mod.compute_metrics(DOCS)
    SUMMARY = mod.summarise([m["words"] for m in METRICS])

    def test_contains_summary_and_leaderboard(self):
        report = mod.render_report(
            self.METRICS, self.SUMMARY, top_n=2, chart_filename=None, engine="pure stdlib fallback"
        )
        assert "_Engine: pure stdlib fallback_" in report
        assert "**100**" in report  # max words
        assert "| [[Long]] | 100 |" in report
        # top_n truncation: Short (3 words) must not appear.
        assert "[[Short]]" not in report

    def test_chart_embed_line_when_provided(self):
        report = mod.render_report(
            self.METRICS,
            self.SUMMARY,
            5,
            chart_filename="Vault Analytics.png",
            engine="pandas + matplotlib",
        )
        assert "![Word count histogram](Vault Analytics.png)" in report

    def test_no_notes_case(self):
        report = mod.render_report([], {}, 5, None, "x")
        assert "_No notes found._" in report


# ---------------------------------------------------------------------------
# optional-deps plumbing
# ---------------------------------------------------------------------------


class TestEngineSelection:
    def test_labels_reflect_module_flags(self, monkeypatch):
        monkeypatch.setattr(mod, "HAS_PANDAS", True, raising=False)
        monkeypatch.setattr(mod, "HAS_MPL", False, raising=False)
        label, chart = mod.pick_engine(create_chart_requested=True)
        assert label == "pandas (no matplotlib)" and chart is False

    def test_full_stack_enables_chart_when_requested(self, monkeypatch):
        monkeypatch.setattr(mod, "HAS_PANDAS", True, raising=False)
        monkeypatch.setattr(mod, "HAS_MPL", True, raising=False)
        _, chart = mod.pick_engine(True)
        assert chart is True


# ---------------------------------------------------------------------------
# run() with fake bridge (stdlib path forced)
# ---------------------------------------------------------------------------


@pytest.fixture()
def analytics_bridge(bind_client, fake_bridge, monkeypatch):
    monkeypatch.setattr(mod, "HAS_PANDAS", False, raising=False)
    monkeypatch.setattr(mod, "HAS_MPL", False, raising=False)
    fake_bridge.get_all_note_paths.return_value = list(DOCS.keys())
    fake_bridge.get_note_content.side_effect = lambda p: DOCS[p]
    return fake_bridge


class TestRun:
    def test_dashboard_created_without_chart(self, analytics_bridge):
        mod.run(analytics_bridge)

        path, content = analytics_bridge.create_note.call_args[0]
        assert path.endswith("Vault Analytics.md")
        assert "pure stdlib fallback" in content
        assert ".png" not in content

    def test_empty_vault_short_circuits(self, bind_client, fake_bridge, monkeypatch):
        bind_client(mod)
        monkeypatch.setattr(mod, "HAS_PANDAS", False, raising=False)
        fake_bridge.get_all_note_paths.return_value = []

        mod.run(fake_bridge)

        fake_bridge.create_note.assert_not_called()
