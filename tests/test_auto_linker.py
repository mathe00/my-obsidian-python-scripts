"""Unit tests for script-auto-linker.py (the heavy artillery).

Covers every pure function exhaustively plus the ``run()`` orchestration
against a fully mocked bridge client. Known heuristic limitations of
``is_inside_link_or_code`` are pinned with ``xfail`` markers so any future fix
(or regression) surfaces loudly.
"""

import urllib.parse

import pytest
from conftest import load_script

mod = load_script("script-auto-linker.py")


# ---------------------------------------------------------------------------
# remove_accents
# ---------------------------------------------------------------------------


class TestRemoveAccents:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("café", "cafe"),
            ("ÉLÈVE", "ELEVE"),
            ("Café Crème", "Cafe Creme"),
            ("naïve résumé", "naive resume"),
            ("plain ascii", "plain ascii"),
            ("", ""),
        ],
    )
    def test_common_cases(self, raw, expected):
        assert mod.remove_accents(raw) == expected

    def test_non_string_passthrough(self):
        sentinel = object()
        assert mod.remove_accents(sentinel) is sentinel

    def test_ligature_not_decomposed(self):
        # NFD does not decompose ligatures: documented behaviour.
        assert mod.remove_accents("cœur") == "cœur"


# ---------------------------------------------------------------------------
# is_inside_link_or_code
# ---------------------------------------------------------------------------


class TestIsInsideLinkOrCode:
    def test_plain_text_is_outside(self):
        assert mod.is_inside_link_or_code(4, "just some words") is False

    def test_inside_wikilink(self):
        content = "[[Machine Learning]]"
        assert mod.is_inside_link_or_code(5, content) is True

    def test_inside_markdown_url(self):
        content = "[label](target.md)"
        # Index inside the parentheses section.
        assert mod.is_inside_link_or_code(len(content) - 3, content) is True

    def test_inside_inline_code(self):
        content = "run `Machine Learning` now"
        idx = content.index("Machine") + 3
        assert mod.is_inside_link_or_code(idx, content) is True

    def test_inside_fenced_block(self):
        content = "```python\nMachine Learning\n```"
        idx = content.index("Machine") + 2
        assert mod.is_inside_link_or_code(idx, content) is True

    def test_after_closed_fenced_block(self):
        # Conservative (documented) heuristic: rfind('```') lands on the CLOSING
        # fence and no re-opening fence follows, so everything after one closed
        # fenced block is treated as inside code and skipped.
        content = "```python\ncode\n```\nAfter the block"
        idx = content.index("After")
        assert mod.is_inside_link_or_code(idx, content) is True


# ---------------------------------------------------------------------------
# split_frontmatter
# ---------------------------------------------------------------------------


class TestSplitFrontmatter:
    def test_no_frontmatter(self):
        fm, body = mod.split_frontmatter("# Title\nbody")
        assert fm == ""
        assert body == "# Title\nbody"

    def test_first_line_not_delimiter(self):
        fm, body = mod.split_frontmatter("tags: x\n---\nbody")
        assert fm == ""
        assert body == "tags: x\n---\nbody"

    def test_valid_frontmatter_split(self):
        content = "---\ntitle: X\ntags: [a]\n---\nBody here."
        fm, body = mod.split_frontmatter(content)
        assert fm == "---\ntitle: X\ntags: [a]\n---"
        assert body == "Body here."

    def test_unclosed_frontmatter_returns_unchanged(self):
        content = "---\ntitle: X\nno closing delimiter"
        fm, body = mod.split_frontmatter(content)
        assert fm == ""
        assert body == content

    def test_empty_body_after_frontmatter(self):
        fm, body = mod.split_frontmatter("---\nk: v\n---")
        assert fm == "---\nk: v\n---"
        assert body == ""

    def test_multiline_frontmatter_preserved_verbatim(self):
        fm_src = "---\naliases:\n  - One\n  - Two\nstatus: draft\n---"
        fm, body = mod.split_frontmatter(fm_src + "\nrest")
        assert fm == fm_src
        assert body == "rest"


# ---------------------------------------------------------------------------
# reconstruct
# ---------------------------------------------------------------------------


class TestReconstruct:
    def test_joins_with_newline_when_missing(self):
        assert mod.reconstruct("---\nk: v\n---", "body") == "---\nk: v\n---\nbody"

    def test_keeps_existing_trailing_newline(self):
        assert mod.reconstruct("---\nk: v\n---\n", "body") == "---\nk: v\n---\nbody"

    def test_body_only(self):
        assert mod.reconstruct("", "body") == "body"

    def test_frontmatter_only(self):
        assert mod.reconstruct("---\nk: v\n---", "") == "---\nk: v\n---"


# ---------------------------------------------------------------------------
# create_links_v3 — matching matrix
# ---------------------------------------------------------------------------

TITLES = {"Machine Learning", "Café", "Learning"}
PATHS = {
    "Machine Learning": "notes/Machine Learning.md",
    "Café": "food/café.md",
    "Learning": "concepts/Learning.md",
}


def link(body, link_type="wikilink", preserve_case=True, ignore_accents=True, match_punct=True):
    return mod.create_links_v3(
        body, TITLES, PATHS, link_type, preserve_case, ignore_accents, match_punct
    )


class TestCreateLinksMatching:
    def test_basic_wikilink_exact_case(self):
        out, changed = link("I study Machine Learning.")
        assert changed is True
        assert out == "I study [[Machine Learning|Machine Learning]]."

    def test_wikilink_different_case_keeps_matched_text(self):
        out, _ = link("i love machine learning ok")
        assert out == "i love [[Machine Learning|machine learning]] ok"

    def test_preserve_case_false_uses_canonical_title(self):
        out, _ = link("go machine learning!", preserve_case=False)
        assert out == "go [[Machine Learning|Machine Learning]]!"

    def test_simple_wikilink_type(self):
        out, _ = link("go machine learning!", link_type="simple_wikilink")
        assert out == "go [[Machine Learning]]!"

    def test_markdown_link_encodes_path(self):
        out, changed = link("read Machine Learning now", link_type="markdown")
        expected_path = urllib.parse.quote("notes/Machine Learning.md")
        assert out == f"read [Machine Learning]({expected_path}) now"
        assert changed is True

    def test_markdown_link_missing_path_falls_back_to_raw_text(self):
        broken_paths = dict(PATHS)
        broken_paths.pop("Machine Learning")
        out, changed = mod.create_links_v3(
            "see Machine Learning.", TITLES, broken_paths, "markdown", True, True, True
        )
        # Documented quirk: text left as-is but the change flag is still raised.
        assert out == "see Machine Learning."
        assert changed is True

    def test_ignore_accents_matches_accentless_text(self):
        out, changed = link("un cafe bien chaud")
        assert changed is True
        assert out == "un [[Café|cafe]] bien chaud"

    def test_accents_respected_when_disabled(self):
        out, changed = link("un cafe bien chaud", ignore_accents=False)
        assert changed is False
        assert out == "un cafe bien chaud"

    def test_match_punctuation_false_leaves_comma_in_stream(self):
        out, _ = link("machine learning, etc", match_punct=False)
        # Zero-width \\b boundary: comma stays attached to following text.
        assert out == "[[Machine Learning|machine learning]], etc"

    def test_longest_title_wins_over_prefix(self):
        out, _ = link("Deep Machine Learning dive")
        # 'Learning' alone must NOT be linked separately inside the longer match.
        assert out.count("[[") == 1
        assert "[[Machine Learning|" in out

    def test_multiple_occurrences_all_linked(self):
        out, _ = link("Machine Learning and more Machine Learning")
        assert out.count("[[Machine Learning|") == 2

    def test_no_titles_returns_unchanged(self):
        out, changed = mod.create_links_v3("body", set(), {}, "wikilink", True, True, True)
        assert out == "body"
        assert changed is False

    def test_empty_body_returns_unchanged(self):
        out, changed = link("")
        assert out == ""
        assert changed is False

    def test_word_boundary_avoids_substring_hits(self):
        out, changed = link("Relearning is not Learning")
        assert changed is True
        # Only standalone 'Learning' at the end gets linked; 'Relearning' untouched.
        assert out == "Relearning is not [[Learning|Learning]]"


class TestCreateLinksProtection:
    def test_existing_wikilink_not_relinked(self):
        out, changed = link("see [[Machine Learning]] please")
        assert changed is False
        assert out == "see [[Machine Learning]] please"

    def test_inline_code_protected(self):
        _, changed = link("snippet `Machine Learning` here")
        assert changed is False

    def test_fenced_block_protected(self):
        body = "```text\nMachine Learning\n```\nend"
        _, changed = link(body)
        assert changed is False

    def test_title_as_markdown_link_text(self):
        # Pinned behaviour: the punctuation class '[\\s.,;!?()]' contains an
        # UNESCAPED ']' which silently closes the class — so ']' is never an
        # accepted trailing char. A title directly followed by ']' therefore
        # produces NO regex match at all, which incidentally protects every
        # existing link syntax ending with brackets. Fragile but intentional
        # to preserve; see README "Known limitations".
        out, changed = link("[Machine Learning](notes/x.md)")
        assert changed is False
        assert out == "[Machine Learning](notes/x.md)"

    def test_bracket_never_counts_as_trailing_punctuation(self):
        # Direct pin of the regex-class quirk described above.
        out, changed = link("word] tail", link_type="simple_wikilink")
        assert changed is False
        assert out == "word] tail"

    def test_dot_still_counts_as_trailing_punctuation(self):
        out, _ = link("Learning. tail", link_type="simple_wikilink")
        assert out == "[[Learning]]. tail"


# ---------------------------------------------------------------------------
# run() — orchestration against fake bridge
# ---------------------------------------------------------------------------


@pytest.fixture()
def linker_bridge(bind_client, fake_bridge):
    bind_client(mod)
    fake_bridge.get_active_note_absolute_path.return_value = "/vault/Notes/daily.md"
    fake_bridge.get_all_note_paths.return_value = sorted(PATHS.values())
    # Rebuild the title->path expectations from real filenames.
    fake_bridge.get_active_note_content.return_value = (
        "---\ndate: 2026-01-01\n---\nToday I study machine learning."
    )
    return fake_bridge


class TestRun:
    def test_happy_path_default_settings(self, linker_bridge):
        mod.run(linker_bridge)

        args, _ = linker_bridge.modify_note_content.call_args
        written = args[1]
        # Frontmatter untouched...
        assert written.startswith("---\ndate: 2026-01-01\n---\n")
        # ...and the body got the piped wikilink with canonical target.
        assert "[[Machine Learning|machine learning]]" in written
        linker_bridge.modify_note_content.assert_called_once()

    def test_settings_values_are_honoured(self, linker_bridge):
        linker_bridge.get_script_settings.return_value = {"link_type": "simple_wikilink"}

        mod.run(linker_bridge)

        written = linker_bridge.modify_note_content.call_args[0][1]
        assert "[[Machine Learning]]" in written
        assert "|machine learning]]" not in written

    def test_settings_error_falls_back_to_defaults(self, linker_bridge, bridge_stub):
        linker_bridge.get_script_settings.side_effect = bridge_stub.ObsidianCommError("boom")

        mod.run(linker_bridge)

        # Defaults: piped wikilink.
        written = linker_bridge.modify_note_content.call_args[0][1]
        assert "[[Machine Learning|machine learning]]" in written

    def test_no_vault_notes_exits_cleanly(self, linker_bridge):
        linker_bridge.get_all_note_paths.return_value = []

        with pytest.raises(SystemExit) as excinfo:
            mod.run(linker_bridge)

        assert excinfo.value.code == 0
        linker_bridge.modify_note_content.assert_not_called()

    def test_paths_error_exits_1(self, linker_bridge, bridge_stub):
        linker_bridge.get_all_note_paths.side_effect = bridge_stub.ObsidianCommError("vault error")

        with pytest.raises(SystemExit) as excinfo:
            mod.run(linker_bridge)

        assert excinfo.value.code == 1

    def test_none_content_exits_1(self, linker_bridge):
        linker_bridge.get_active_note_content.return_value = None

        with pytest.raises(SystemExit) as excinfo:
            mod.run(linker_bridge)

        assert excinfo.value.code == 1

    def test_no_matches_notifies_and_skips_write(self, linker_bridge):
        linker_bridge.get_active_note_content.return_value = "nothing relevant here at all"

        mod.run(linker_bridge)

        linker_bridge.modify_note_content.assert_not_called()
        assert any(
            "No new links" in str(c.args[0]) for c in linker_bridge.show_notification.call_args_list
        )

    def test_write_failure_exits_1(self, linker_bridge, bridge_stub):
        linker_bridge.modify_note_content.side_effect = bridge_stub.ObsidianCommError("disk full")

        with pytest.raises(SystemExit) as excinfo:
            mod.run(linker_bridge)

        assert excinfo.value.code == 1

    def test_missing_note_path_exits_1(self, linker_bridge, bridge_stub):
        linker_bridge.get_active_note_absolute_path.side_effect = bridge_stub.ObsidianCommError(
            "no note"
        )

        with pytest.raises(SystemExit) as excinfo:
            mod.run(linker_bridge)

        assert excinfo.value.code == 1
