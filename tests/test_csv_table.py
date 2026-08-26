"""Unit tests for csv-to-markdown-table.py."""

import pytest
from conftest import load_script

mod = load_script("csv-to-markdown-table.py")


# ---------------------------------------------------------------------------
# heuristics & sniffing
# ---------------------------------------------------------------------------


class TestLooksLikeCsv:
    def test_comma_rows(self):
        assert mod.looks_like_csv("a,b\n1,2") is True

    def test_semicolon_rows(self):
        assert mod.looks_like_csv("a;b\n1;2") is True

    def test_single_line_rejected(self):
        assert mod.looks_like_csv("a,b,c") is False

    def test_plain_text_rejected(self):
        assert mod.looks_like_csv("hello world\nsecond line") is False


class TestSniffDelimiter:
    def test_override_wins(self):
        assert mod.sniff_delimiter("a,b", override=";") == ";"

    def test_sniffer_semicolon(self):
        assert mod.sniff_delimiter("a;b;c") == ";"

    def test_fallback_comma_on_ambiguity(self):
        assert mod.sniff_delimiter("justonecell") == ","


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


class TestParseCsv:
    def test_basic_header_and_rows(self):
        headers, rows = mod.parse_csv("name,age\nalice,30\nbob,25")
        assert headers == ["name", "age"]
        assert rows == [["alice", "30"], ["bob", "25"]]

    def test_quoted_commas_preserved(self):
        _headers, rows = mod.parse_csv('name,note\n"Doe, John","likes, commas"')
        assert rows == [["Doe, John", "likes, commas"]]

    def test_ragged_rows_padded(self):
        _headers, rows = mod.parse_csv("a,b,c\n1,2")
        assert len(rows[0]) == 3 and rows[0][2] == ""

    def test_no_header_generates_names(self):
        headers, rows = mod.parse_csv("1,2\n3,4", has_header=False)
        assert headers == ["C1", "C2"]
        assert rows == [["1", "2"], ["3", "4"]]

    def test_blank_lines_skipped(self):
        _headers, rows = mod.parse_csv("h1,h2\n\nv1,v2\n")
        assert rows == [["v1", "v2"]]

    def test_empty_text(self):
        assert mod.parse_csv("") == ([], [])


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


class TestRenderTable:
    def test_pipes_escaped_and_alignment_row(self):
        table = mod.render_md_table(["k|v"], [["a|b"]])
        lines = table.splitlines()
        assert "\\|" in lines[0] and "\\|" in lines[2]
        assert set(lines[1]) <= {"-", "|"}

    def test_column_alignment_padding(self):
        table = mod.render_md_table(["id", "name"], [["1", "leo"], ["42", "bo"]])
        data_lines = table.splitlines()[2:]
        # Both rows padded to same width -> identical structure positions.
        assert len(data_lines[0]) == len(data_lines[1])

    def test_newline_in_cell_flattened(self):
        table = mod.render_md_table(["c"], [["line1\nline2"]])
        assert "<br>" in table and "\nline2" not in table.splitlines()[2]

    def test_empty_headers_empty_output(self):
        assert mod.render_md_table([], []) == ""


class TestTransform:
    def test_end_to_end(self):
        table = mod.transform_csv_to_table("lang,cool\npython,very")
        lines = table.splitlines()
        # Header padded to widest cell in its column ('python').
        assert lines[0].split() == ["|", "lang", "|", "cool", "|"]
        assert set(lines[1]) <= {"-", "|"}
        assert "python" in lines[2]


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


@pytest.fixture()
def csv_bridge(bind_client, fake_bridge):
    return bind_client(mod)


class TestRun:
    def test_selection_replaced_with_table(self, csv_bridge):
        csv_bridge.get_selected_text.return_value = "x,y\n1,2"

        mod.run(csv_bridge)

        args, _ = csv_bridge.replace_selected_text.call_args
        assert args[0].splitlines()[0] == "| x | y |"

    def test_modal_path_appends_to_note(self, csv_bridge):
        csv_bridge.get_selected_text.return_value = ""
        csv_bridge.request_user_input.return_value = "a;b\n1;2"
        csv_bridge.get_active_note_absolute_path.return_value = "/v/n.md"
        csv_bridge.get_active_note_content.return_value = "# Title"

        mod.run(csv_bridge)

        written = csv_bridge.modify_note_content.call_args[0][1]
        assert written.startswith("# Title")
        assert "| a | b |" in written

    def test_cancelled_modal_exits_cleanly(self, csv_bridge, bridge_stub):
        csv_bridge.get_selected_text.return_value = ""
        csv_bridge.request_user_input.side_effect = bridge_stub.ObsidianCommError("cancelled")

        mod.run(csv_bridge)  # No SystemExit: friendly notify instead.

        csv_bridge.modify_note_content.assert_not_called()

    def test_garbage_input_notifies_failure(self, csv_bridge):
        csv_bridge.get_selected_text.return_value = "\n\n"

        mod.run(csv_bridge)

        csv_bridge.replace_selected_text.assert_not_called()
