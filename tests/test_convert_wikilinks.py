"""Unit tests for convert_all_basic_obsidian_links_into_wikilinks.py."""

import sys

import pytest
from conftest import load_script

mod = load_script("convert_all_basic_obsidian_links_into_wikilinks.py")


# ---------------------------------------------------------------------------
# replace_simple_links_with_wikilinks (pure, per-line)
# ---------------------------------------------------------------------------


class TestReplaceSimpleLinks:
    def test_simple_link_converted(self):
        assert mod.replace_simple_links_with_wikilinks("[[Note]]") == "[[Note|Note]]"

    def test_piped_link_untouched(self):
        line = "[[Note|Alias]]"
        assert mod.replace_simple_links_with_wikilinks(line) == line

    def test_multiple_links_same_line(self):
        result = mod.replace_simple_links_with_wikilinks("[[A]] and [[B]]")
        assert result == "[[A|A]] and [[B|B]]"

    def test_mixed_piped_and_simple(self):
        result = mod.replace_simple_links_with_wikilinks("[[Piped|Alias]] then [[Simple]]")
        assert result == "[[Piped|Alias]] then [[Simple|Simple]]"

    def test_no_links_unchanged(self):
        line = "Just plain text with no links at all."
        assert mod.replace_simple_links_with_wikilinks(line) == line

    def test_empty_string(self):
        assert mod.replace_simple_links_with_wikilinks("") == ""

    def test_path_like_link(self):
        # Slashes are valid inside wikilink targets.
        assert (
            mod.replace_simple_links_with_wikilinks("[[folder/sub note]]")
            == "[[folder/sub note|folder/sub note]]"
        )

    def test_unclosed_bracket_not_touched(self):
        line = "This is [not a wikilink]"
        assert mod.replace_simple_links_with_wikilinks(line) == line

    def test_markdown_link_not_touched(self):
        line = "[text](target.md)"
        assert mod.replace_simple_links_with_wikilinks(line) == line


# ---------------------------------------------------------------------------
# process_lines (pure, whole-note with frontmatter awareness)
# ---------------------------------------------------------------------------


class TestProcessLines:
    def test_body_links_converted_and_flag_set(self):
        lines = ["# Title", "See [[Target]] today."]
        new_lines, changed = mod.process_lines(lines)
        assert changed is True
        assert new_lines == ["# Title", "See [[Target|Target]] today."]

    def test_frontmatter_content_preserved(self):
        lines = ["---", "tags: [[inline-link-in-fm]]", "---", "Body [[Real]]."]
        new_lines, changed = mod.process_lines(lines)
        assert changed is True
        assert new_lines[1] == "tags: [[inline-link-in-fm]]"  # Untouched.
        assert new_lines[3] == "Body [[Real|Real]]."

    def test_no_changes_flag_false(self):
        lines = ["---", "title: x", "---", "nothing here"]
        new_lines, changed = mod.process_lines(lines)
        assert changed is False
        assert new_lines == lines

    def test_horizontal_rule_in_body_is_ignored_as_boundary(self):
        # '---' after the closed frontmatter must not re-open a block.
        lines = ["---", "fm: true", "---", "before", "---", "[[After]]"]
        new_lines, changed = mod.process_lines(lines)
        assert changed is True
        assert new_lines[5] == "[[After|After]]"

    def test_unclosed_frontmatter_freezes_whole_document(self):
        # First line opens frontmatter that never closes: nothing is transformed
        # (matches the original conservative behaviour).
        lines = ["---", "draft: true", "[[Never touched]]"]
        new_lines, changed = mod.process_lines(lines)
        assert changed is False
        assert new_lines == lines

    def test_line_count_preserved(self):
        lines = ["a", "[[b]]", "c", "[[d]]", ""]
        new_lines, _ = mod.process_lines(lines)
        assert len(new_lines) == len(lines)


# ---------------------------------------------------------------------------
# run() — orchestration against a fake bridge client
# ---------------------------------------------------------------------------


@pytest.fixture()
def converter_bridge(bind_client, fake_bridge):
    bind_client(mod)  # Activates patching of ObsidianPluginDevPythonToJS().
    return fake_bridge


class TestRun:
    def test_happy_path_writes_joined_content(self, converter_bridge):
        converter_bridge.get_active_note_absolute_path.return_value = "/vault/n.md"
        converter_bridge.get_active_note_content.return_value = ["hello", "see [[X]]"]

        mod.run(converter_bridge)

        converter_bridge.modify_note_content.assert_called_once_with(
            "/vault/n.md", "hello\nsee [[X|X]]"
        )
        # Success notification sent.
        assert any(
            "converted" in str(c.args[0]) for c in converter_bridge.show_notification.call_args_list
        )

    def test_no_change_skips_write(self, converter_bridge):
        converter_bridge.get_active_note_content.return_value = ["plain", "lines"]

        mod.run(converter_bridge)

        converter_bridge.modify_note_content.assert_not_called()

    def test_missing_note_path_exits_1_with_notification(self, converter_bridge, bridge_stub):
        converter_bridge.get_active_note_absolute_path.side_effect = bridge_stub.ObsidianCommError(
            "no active note"
        )

        with pytest.raises(SystemExit) as excinfo:
            mod.run(converter_bridge)

        assert excinfo.value.code == 1
        assert converter_bridge.show_notification.called

    def test_none_content_exits_1(self, converter_bridge):
        converter_bridge.get_active_note_content.return_value = None

        with pytest.raises(SystemExit) as excinfo:
            mod.run(converter_bridge)

        assert excinfo.value.code == 1
        converter_bridge.modify_note_content.assert_not_called()

    def test_wrong_content_type_exits_1(self, converter_bridge):
        converter_bridge.get_active_note_content.return_value = "should have been a list"

        with pytest.raises(SystemExit) as excinfo:
            mod.run(converter_bridge)

        assert excinfo.value.code == 1

    def test_modify_failure_exits_1_with_error_notification(self, converter_bridge, bridge_stub):
        converter_bridge.get_active_note_content.return_value = ["[[X]]"]
        converter_bridge.modify_note_content.side_effect = bridge_stub.ObsidianCommError(
            "write failed"
        )

        with pytest.raises(SystemExit) as excinfo:
            mod.run(converter_bridge)

        assert excinfo.value.code == 1
        assert any(
            "Error saving" in str(c.args[0])
            for c in converter_bridge.show_notification.call_args_list
        )

    def test_module_registered_in_sys_modules(self):
        name = next(n for n in sys.modules if n.startswith("script_under_test_convert"))
        assert sys.modules[name] is mod
