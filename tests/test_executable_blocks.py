"""Unit tests for executable-code-blocks.py."""

import pytest
from conftest import load_script

mod = load_script("executable-code-blocks.py")


# ---------------------------------------------------------------------------
# parse_run_blocks
# ---------------------------------------------------------------------------


class TestParseRunBlocks:
    def test_tagged_python_block_found(self):
        content = "intro\n```python #run\nprint('x')\n```\noutro"
        blocks = mod.parse_run_blocks(content)
        assert len(blocks) == 1
        assert blocks[0].code == "print('x')"
        assert blocks[0].open_line == 1 and blocks[0].close_line == 3

    def test_untagged_block_ignored(self):
        assert mod.parse_run_blocks("```python\nprint(1)\n```") == []

    def test_other_language_ignored(self):
        assert mod.parse_run_blocks("```js #run\nconsole.log(1)\n```") == []

    def test_multiple_blocks_in_order(self):
        content = "```python #run\na=1\n```\ntext\n```python #run\nb=2\n```"
        blocks = mod.parse_run_blocks(content)
        assert [b.code for b in blocks] == ["a=1", "b=2"]

    def test_unclosed_fence_skipped_safely(self):
        assert mod.parse_run_blocks("```python #run\nnever closed") == []


# ---------------------------------------------------------------------------
# execute_code
# ---------------------------------------------------------------------------


class TestExecuteCode:
    def test_stdout_captured(self):
        ok, out = mod.execute_code("print('hello'); print('world')")
        assert ok is True
        assert out == "hello\nworld\n"

    def test_exception_captured_not_raised(self):
        ok, out = mod.execute_code("raise ValueError('boom')")
        assert ok is False
        assert "ValueError: boom" in out

    def test_syntax_error_reported(self):
        ok, out = mod.execute_code("def broken(:")
        assert ok is False
        assert out  # some diagnostic text present

    def test_isolated_namespace_between_runs(self):
        mod.execute_code("secret = 42")
        ok, _out = mod.execute_code("print(secret)")
        assert ok is False  # NameError -> isolated namespaces confirmed


# ---------------------------------------------------------------------------
# render_result / inject / full pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_render_result_success_callout(self):
        rendered = mod.render_result(True, "1024", 1500)
        assert "> [!success] Result" in rendered
        assert "> 1024" in rendered
        assert mod.RESULT_START in rendered and mod.RESULT_END in rendered

    def test_render_result_truncation_and_empty(self):
        long_out = mod.render_result(True, "z" * 5000, 100)
        assert "(truncated)" in long_out and len(long_out) < 400
        empty_out = mod.render_result(False, "", 100)
        assert "(no output)" in empty_out

    def test_full_pipeline_idempotent(self):
        note = "# NB\n```python #run\nprint('v1')\n```\nend"
        once, n_ok, n_err = mod.process_note(note, 1500)
        assert (n_ok, n_err) == (1, 0)
        twice, n_ok2, n_err2 = mod.process_note(once, 1500)
        assert (n_ok2, n_err2) == (1, 0)
        assert twice.count(mod.RESULT_START) == 1
        assert "'v1'" in twice or "v1" in twice  # fresh output present exactly once
        assert twice.count("v1") == once.count("v1")

    def test_pipeline_without_blocks_untouched(self):
        original = "plain note with ```python\ncode\n``` but no tag"
        out, n_ok, n_err = mod.process_note(original, 1500)
        assert out == original and (n_ok, n_err) == (0, 0)

    def test_mixed_ok_and_error_counts(self):
        note = "```python #run\nprint(1)\n```\n\n```python #run\n1/0\n```"
        _, n_ok, n_err = mod.process_note(note, 1500)
        assert (n_ok, n_err) == (1, 1)


# ---------------------------------------------------------------------------
# run() with fake bridge
# ---------------------------------------------------------------------------


@pytest.fixture()
def exec_bridge(bind_client, fake_bridge):
    fake_bridge.get_active_note_absolute_path.return_value = "/vault/nb.md"
    return fake_bridge


class TestRun:
    def test_happy_path_writes_results(self, exec_bridge):
        exec_bridge.get_active_note_content.return_value = "```python #run\nprint('hi')\n```"

        mod.run(exec_bridge)

        written = exec_bridge.modify_note_content.call_args[0][1]
        assert "> hi" in written
        exec_bridge.modify_note_content.assert_called_once()

    def test_no_blocks_notifies_only(self, exec_bridge):
        exec_bridge.get_active_note_content.return_value = "# nothing runnable"

        mod.run(exec_bridge)

        exec_bridge.modify_note_content.assert_not_called()
        assert any("#run" in str(c.args[0]) for c in exec_bridge.show_notification.call_args_list)
