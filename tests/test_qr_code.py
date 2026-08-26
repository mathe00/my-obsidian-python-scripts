"""Unit tests for qr-code-generator.py (renderer injected — qrcode never needed)."""

import pytest
from conftest import load_script

mod = load_script("qr-code-generator.py")


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self):
        assert mod.slugify("Hello World!") == "hello-world"

    def test_accents_stripped(self):
        assert mod.slugify("Café Crème") == "cafe-creme"

    def test_max_length_truncation(self):
        assert len(mod.slugify("a" * 100, max_len=32)) == 32

    def test_garbage_becomes_default(self):
        assert mod.slugify("///") == "qr"


class TestNaming:
    def test_unique_filename_shape(self):
        name = mod.unique_filename("https://example.com")
        assert name.startswith("https-example-com-") or name.startswith("http-example-com")
        assert name.endswith(".png")
        parts = name[:-4].rsplit("-", 1)
        assert len(parts[1]) == 8  # hash suffix

    def test_same_input_stable_name(self):
        assert mod.unique_filename("abc") == mod.unique_filename("abc")

    def test_embed_format(self):
        assert mod.build_embed_markdown("x.png") == "![[x.png]]"


# ---------------------------------------------------------------------------
# run() — renderer injected via monkeypatch
# ---------------------------------------------------------------------------


@pytest.fixture()
def qr_bridge(bind_client, fake_bridge, monkeypatch):
    # Force the "dependency present" branch: the renderer itself is injected
    # per-test, so the real qrcode lib is never required.
    monkeypatch.setattr(mod, "HAS_QRCODE", True, raising=False)
    fake_bridge.get_current_vault_absolute_path.return_value = "/vault"
    fake_bridge.check_path_exists.return_value = False
    return fake_bridge


class TestRun:
    def _patch_renderer(self, monkeypatch, result=True):
        calls = {}

        def fake_render(text, path):
            calls["text"], calls["path"] = text, path
            return result

        monkeypatch.setattr(mod, "make_qr_png", fake_render)
        return calls

    def test_selection_flow_replaces_with_embed(self, qr_bridge, monkeypatch):
        calls = self._patch_renderer(monkeypatch)
        qr_bridge.get_selected_text.return_value = "https://obsidian.md"

        mod.run(qr_bridge)

        assert calls["text"] == "https://obsidian.md"
        assert calls["path"].startswith("/vault/Attachments/")
        embed_arg = qr_bridge.replace_selected_text.call_args[0][0]
        assert embed_arg.startswith("![[") and embed_arg.endswith(".png]]")

    def test_missing_folder_created_via_bridge(self, qr_bridge, monkeypatch):
        self._patch_renderer(monkeypatch)
        qr_bridge.get_selected_text.return_value = "payload"

        mod.run(qr_bridge)

        qr_bridge.create_folder.assert_called_once()

    def test_existing_folder_skips_creation(self, qr_bridge, monkeypatch):
        self._patch_renderer(monkeypatch)
        qr_bridge.check_path_exists.return_value = True
        qr_bridge.get_selected_text.return_value = "payload"

        mod.run(qr_bridge)

        qr_bridge.create_folder.assert_not_called()

    def test_renderer_failure_blocks_write(self, qr_bridge, monkeypatch):
        self._patch_renderer(monkeypatch, result=False)
        qr_bridge.get_selected_text.return_value = "payload"

        mod.run(qr_bridge)

        qr_bridge.replace_selected_text.assert_not_called()
        qr_bridge.modify_note_content.assert_not_called()

    def test_no_selection_modal_cancelled_exits(self, qr_bridge, monkeypatch, bridge_stub):
        self._patch_renderer(monkeypatch)
        qr_bridge.get_selected_text.return_value = ""
        qr_bridge.request_user_input.side_effect = bridge_stub.ObsidianCommError("cancel")

        mod.run(qr_bridge)

        qr_bridge.modify_note_content.assert_not_called()

    def test_missing_dep_hint(self, qr_bridge, monkeypatch):
        monkeypatch.setattr(mod, "HAS_QRCODE", False, raising=False)
        qr_bridge.get_selected_text.return_value = "whatever"

        mod.run(qr_bridge)

        assert any(
            "pip install qrcode" in str(c.args[0])
            for c in qr_bridge.show_notification.call_args_list
        )

    def test_append_flow_when_no_selection_but_modal_ok(self, qr_bridge, monkeypatch):
        self._patch_renderer(monkeypatch)
        qr_bridge.get_selected_text.return_value = ""
        qr_bridge.request_user_input.return_value = "modal text"
        qr_bridge.get_active_note_absolute_path.return_value = "/vault/n.md"
        qr_bridge.get_active_note_content.return_value = "# Note"

        mod.run(qr_bridge)

        written = qr_bridge.modify_note_content.call_args[0][1]
        assert written.startswith("# Note") and "![[modal-text-" in written
