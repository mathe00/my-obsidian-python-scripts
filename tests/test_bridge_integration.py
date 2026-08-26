"""Integration tests running the scripts against the REAL current OPB library.

These tests locate the local Obsidian Python Bridge dev clone, point
``PYTHONPATH`` at it and execute the scripts in subprocesses:

* **Event guard** — with ``OBSIDIAN_EVENT_NAME`` set, every script must exit 0
  immediately (before any client/HTTP init). This validates that our scripts
  follow the *current* recommended structure of the plugin.
* **Settings discovery** — with ``--get-settings-json``, scripts must print a
  valid JSON array of their setting definitions on stdout. This is exactly
  what the plugin runs at startup.

Self-skipping when no OPB clone exists (e.g. CI checkout without the vault).
"""

import json

from conftest import run_script_subprocess


class TestEventGuard:
    def test_converter_exits_zero_on_event(self):
        proc = run_script_subprocess(
            "convert_all_basic_obsidian_links_into_wikilinks.py",
            {"OBSIDIAN_EVENT_NAME": "vault-modify"},
            [],
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        assert "Traceback" not in proc.stderr

    def test_auto_linker_exits_zero_on_event(self):
        proc = run_script_subprocess(
            "script-auto-linker.py",
            {"OBSIDIAN_EVENT_NAME": "vault-modify"},
            [],
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        assert "Traceback" not in proc.stderr

    def test_define_word_exits_zero_on_event(self):
        proc = run_script_subprocess(
            "define_word_en_concise.py",
            {"OBSIDIAN_EVENT_NAME": "active-leaf-change"},
            [],
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"


class TestSettingsDiscovery:
    def test_converter_discovery_returns_empty_list(self):
        proc = run_script_subprocess(
            "convert_all_basic_obsidian_links_into_wikilinks.py", {}, ["--get-settings-json"]
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        assert json.loads(proc.stdout) == []

    def test_define_word_discovery_returns_empty_list(self):
        proc = run_script_subprocess("define_word_en_concise.py", {}, ["--get-settings-json"])
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        assert json.loads(proc.stdout) == []

    def test_auto_linker_discovery_returns_full_settings(self):
        proc = run_script_subprocess("script-auto-linker.py", {}, ["--get-settings-json"])
        assert proc.returncode == 0, f"stderr: {proc.stderr}"

        definitions = json.loads(proc.stdout)
        keys = [d["key"] for d in definitions]
        assert keys == ["link_type", "preserve_case", "ignore_accents", "match_punctuation"]

        by_key = {d["key"]: d for d in definitions}
        assert by_key["link_type"]["type"] == "dropdown"
        assert set(by_key["link_type"]["options"]) == {"wikilink", "simple_wikilink", "markdown"}
        for toggle in ("preserve_case", "ignore_accents", "match_punctuation"):
            assert by_key[toggle]["type"] == "toggle"
            assert isinstance(by_key[toggle]["default"], bool)
