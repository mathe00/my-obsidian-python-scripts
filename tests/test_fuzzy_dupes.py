"""Unit tests for fuzzy-duplicate-finder.py."""

import pytest
from conftest import load_script

mod = load_script("fuzzy-duplicate-finder.py")


# ---------------------------------------------------------------------------
# title similarity
# ---------------------------------------------------------------------------


class TestSimilarTitlePairs:
    def test_identical_normalised_titles_score_one(self):
        pairs = mod.similar_title_pairs(["My Note", "MY   NOTE"], threshold=0.9)
        assert pairs == [("My Note", "MY   NOTE", 1.0)]

    def test_near_duplicates_caught(self):
        pairs = mod.similar_title_pairs(["Reading List", "Reading List 2024"], threshold=0.75)
        names = {(a, b) for a, b, _ in pairs}
        assert any({"Reading List", "Reading List 2024"} == set(pair) for pair in names)

    def test_unrelated_titles_filtered_by_threshold(self):
        assert mod.similar_title_pairs(["Python", "Gardening"], threshold=0.85) == []

    def test_threshold_zero_returns_everything(self):
        assert len(mod.similar_title_pairs(["A", "B"], threshold=0.0)) == 1

    def test_sorted_by_score_descending(self):
        titles = ["Project Alpha", "project alpha ", "Completely Different Thing"]
        pairs = mod.similar_title_pairs(titles, threshold=0.5)
        scores = [s for _, _, s in pairs]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# body duplicates
# ---------------------------------------------------------------------------


class TestBodyGroups:
    def test_exact_duplicates_grouped(self):
        groups = mod.exact_body_groups(
            {"A": "same body here", "B": "Same  Body   Here".lower(), "C": "different"}
        )
        assert len(groups) == 1
        assert set(groups[0]) == {"A", "B"}

    def test_whitespace_case_insensitive(self):
        groups = mod.exact_body_groups({"X": "Hello World", "Y": "hello   world", "Z": "other"})
        assert groups and set(groups[0]) == {"X", "Y"}

    def test_all_unique_gives_no_groups(self):
        assert mod.exact_body_groups({"A": "one", "B": "two"}) == []


# ---------------------------------------------------------------------------
# rendering & notification summary
# ---------------------------------------------------------------------------


class TestRenderReport:
    def test_report_sections_present(self):
        report = mod.render_report([("A", "B", 0.92)], [["X", "Y"]])
        assert "[[A]] ↔ [[B]]" in report
        assert "[[X]]" in report and "[[Y]]" in report

    def test_empty_findings_friendly(self):
        report = mod.render_report([], [])
        assert "_None found._" in report

    def test_summary_notification_text(self):
        one_pair = [("A", "B", 0.9)]
        one_group = [["X", "Y"]]
        summary = mod.summarise_notification(one_pair, one_group)
        assert "1 similar title(s)" in summary and "1 identical body group(s)" in summary


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


@pytest.fixture()
def dupes_bridge(bind_client, fake_bridge):
    fake_bridge.get_all_note_paths.return_value = ["Python Tips.md", "python tips.md", "Unique.md"]
    fake_bridge.get_note_content.side_effect = lambda p: {
        "Python Tips.md": "# tips\nuse dataclasses",
        "python tips.md": "# TIPS\nuse dataclasses",
        "Unique.md": "totally different",
    }[p]
    return fake_bridge


class TestRun:
    def test_report_written_with_both_sections(self, dupes_bridge):
        mod.run(dupes_bridge)

        path, content = dupes_bridge.create_note.call_args[0]
        assert path.endswith(".md")
        assert "## Similar titles" in content
        assert "Identical bodies" in content

    def test_body_check_disabled_skips_reads(self, dupes_bridge):
        dupes_bridge.get_script_settings.return_value = {"detect_body_duplicates": False}

        mod.run(dupes_bridge)

        dupes_bridge.get_note_content.assert_not_called()

    def test_single_note_bails_out(self, bind_client, fake_bridge):
        bind_client(mod)
        fake_bridge.get_all_note_paths.return_value = ["Solo.md"]

        mod.run(fake_bridge)

        fake_bridge.create_note.assert_not_called()

    def test_clean_vault_notification(self, bind_client, fake_bridge):
        bind_client(mod)
        fake_bridge.get_all_note_paths.return_value = ["Alpha.md", "Zebra Notes.md"]
        fake_bridge.get_note_content.side_effect = lambda p: {
            "Alpha.md": "aaa",
            "Zebra Notes.md": "bbb",
        }[p]

        mod.run(fake_bridge)

        assert any("clean" in str(c.args[0]) for c in fake_bridge.show_notification.call_args_list)
