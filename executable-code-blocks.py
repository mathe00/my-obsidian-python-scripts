"""
Obsidian Python Bridge Script: Executable Code Blocks (Jupyter-lite POC)

Turn the active note into a lightweight notebook: any fenced Python block
tagged with ``#run`` is executed, its stdout captured and injected right
after the fence as an Obsidian callout:

    ```python #run
    print(2 ** 10)
    ```
    <!-- exec-result:start -->
    > [!quote] Result
   > ```
    > 1024
    > ```
    <!-- exec-result:end -->

Re-running replaces previous results (idempotent). Exceptions are captured
and rendered as an error callout — the note never breaks.

⚠️ SECURITY: this executes arbitrary Python from your note. Only run blocks
you wrote yourself — same trust model as the bridge itself.

Pure helpers are unit-testable; orchestration lives in injectable ``run()``.
"""

import contextlib
import io
import os
import re
import sys
import traceback
from typing import NamedTuple

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
    {
        "key": "max_output_chars",
        "type": "number",
        "label": "Max captured output characters",
        "default": 1500,
    },
]
define_settings(MY_SCRIPT_SETTINGS)
_handle_cli_args()

RESULT_START = "<!-- exec-result:start -->"
RESULT_END = "<!-- exec-result:end -->"

_FENCE_OPEN_RE = re.compile(r"^(\s*)(`{3,})(.*)$")
_TAG_RE = re.compile(r"#run\b")


class RunBlock(NamedTuple):
    """A ```python #run fence located inside the note."""

    open_line: int  # index of the opening fence line
    close_line: int  # index of the closing fence line
    code: str


# --- Pure core ---


def strip_previous_results(content: str) -> str:
    """Remove any previously injected result callouts."""
    pattern = re.compile(
        re.escape(RESULT_START) + r".*?" + re.escape(RESULT_END) + r"\n?", re.DOTALL
    )
    return pattern.sub("", content)


def parse_run_blocks(content: str) -> list[RunBlock]:
    """Find ``python`` fences whose info string contains ``#run``.

    Simple line scanner: nested fences and fences inside code fences are
    unsupported by design (documented POC limitation).
    """
    lines = content.split("\n")
    open_fence: tuple[int, str] | None = None  # (line_idx, info_string)
    blocks: list[RunBlock] = []

    for idx, line in enumerate(lines):
        match = _FENCE_OPEN_RE.match(line)
        if not match:
            continue
        ticks, info = match.group(2), match.group(3).strip()

        if open_fence is None:
            if ticks == "```" and info.startswith("python") and _TAG_RE.search(info):
                open_fence = (idx, info)
        else:
            if set(ticks) == {"`"} and len(ticks) >= 3:
                code = "\n".join(lines[open_fence[0] + 1 : idx])
                blocks.append(RunBlock(open_line=open_fence[0], close_line=idx, code=code))
                open_fence = None

    return blocks


def execute_code(code: str) -> tuple[bool, str]:
    """Run *code* in a fresh namespace; return (ok, captured_output_or_traceback).

    stdout is captured via ``contextlib.redirect_stdout``. Exceptions produce
    the trimmed traceback text instead of propagating.
    """
    buffer = io.StringIO()
    namespace: dict = {"__name__": "__exec_block__"}
    try:
        with contextlib.redirect_stdout(buffer):
            exec(code, namespace)
        return True, buffer.getvalue()
    except Exception:
        return False, "".join(
            traceback.format_exception_only(sys.exc_info()[0], sys.exc_info()[1])
        ).strip()


def render_result(ok: bool, output: str, max_chars: int) -> str:
    """Render one result block as an Obsidian callout wrapped in markers."""
    if len(output) > max_chars:
        output = output[:max_chars] + "\n… (truncated)"
    if not output.strip():
        output = "(no output)"
    status = "success" if ok else "warning"
    title = "Result" if ok else "Error"
    quoted = "\n".join(f"> {line}" for line in output.rstrip("\n").split("\n"))
    body = f"> [!{status}] {title}\n> ```\n{quoted}\n> ```"
    return f"{RESULT_START}\n{body}\n{RESULT_END}\n"


def inject_results(
    content: str, results: list[tuple[RunBlock, bool, str]], max_chars: int
) -> tuple[str, int, int]:
    """Return (new_content, n_ok, n_error) with results inserted after each close fence."""
    lines = content.split("\n")
    n_ok = n_err = 0
    # Insert bottom-up so earlier indices stay valid.
    for block, ok, output in sorted(results, key=lambda pair: pair[0].close_line, reverse=True):
        rendered = render_result(ok, output, max_chars)
        lines.insert(block.close_line + 1, rendered)
        n_ok += ok
        n_err += not ok
    return "\n".join(lines), n_ok, n_err


def process_note(content: str, max_chars: int) -> tuple[str, int, int]:
    """Full pure pipeline: strip old outputs, run tagged blocks, inject fresh ones."""
    cleaned = strip_previous_results(content)
    blocks = parse_run_blocks(cleaned)
    if not blocks:
        return content, 0, 0
    results = [(block, *execute_code(block.code)) for block in blocks]
    return inject_results(cleaned, results, max_chars)


# --- Orchestration ---


def run(obsidian: ObsidianPluginDevPythonToJS) -> None:
    try:
        settings = obsidian.get_script_settings()
        max_chars = int(settings.get("max_output_chars", MY_SCRIPT_SETTINGS[0]["default"]))
    except ObsidianCommError:
        max_chars = 1500

    abs_path = obsidian.get_active_note_absolute_path()
    content = obsidian.get_active_note_content(return_format="string") or ""

    new_content, n_ok, n_err = process_note(content, max_chars)
    if n_ok + n_err == 0:
        obsidian.show_notification("No ```python #run blocks found.", 4000)
        return

    obsidian.modify_note_content(abs_path, new_content)
    obsidian.show_notification(
        f"Executed {n_ok + n_err} block(s): {n_ok} ok, {n_err} error(s)", 5000
    )


if __name__ == "__main__":
    try:
        run(ObsidianPluginDevPythonToJS())
    except ObsidianCommError as e:
        print(f"ERROR: Obsidian Communication Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
