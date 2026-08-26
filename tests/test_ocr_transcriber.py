"""Unit tests for ocr-image-transcriber.py (engine injected — no Tesseract needed)."""

import pytest
from conftest import load_script

mod = load_script("ocr-image-transcriber.py")


# ---------------------------------------------------------------------------
# parsing & rendering
# ---------------------------------------------------------------------------


class TestFindImageLines:
    def test_wiki_and_md_embeds(self):
        content = "![[shot.png]]\ntext\n![alt](folder/pic.jpg)"
        pairs = mod.find_image_lines(content)
        assert pairs == [(0, "shot.png"), (2, "folder/pic.jpg")]

    def test_non_images_ignored_and_dupes_skipped(self):
        content = "[[note.md]]\n![[same.png]]\n![[same.png]]"
        assert len(mod.find_image_lines(content)) == 1

    def test_render_transcription_quotes_text(self):
        rendered = mod.render_transcription("line1\nline2")
        assert "> line1" in rendered and "> line2" in rendered
        assert mod.OCR_START in rendered and mod.OCR_END in rendered

    def test_render_empty_gives_placeholder(self):
        assert "(no text recognised)" in mod.render_transcription("   \n")


# ---------------------------------------------------------------------------
# pipeline idempotency & failure handling
# ---------------------------------------------------------------------------


class TestProcessNote:
    CONTENT = "head\n![[a.png]]\ntail\n![](b.jpg)"

    def test_inserts_under_each_image(self):
        out, done, failed = mod.process_note(
            self.CONTENT,
            engine=lambda path, lang="eng": f"TEXT[{path}]",
            language="eng",
            max_images=5,
        )
        assert done == 2 and failed == 0
        lines = out.split("\n")
        a_idx = next(i for i, line in enumerate(lines) if line == "![[a.png]]")
        window = "\n".join(lines[a_idx + 1 : a_idx + 6])
        assert mod.OCR_START in window and "TEXT[a.png]" in window

    def test_idempotent_second_run_replaces(self):
        once, _, _ = mod.process_note(self.CONTENT, lambda p, lang="eng": "v1", "eng", 5)
        twice, done, _ = mod.process_note(once, lambda p, lang="eng": "v2", "eng", 5)
        assert twice.count(mod.OCR_START) == 2
        assert "v1" not in twice and "v2" in twice and done == 2

    def test_engine_failure_marks_unreadable(self):
        def boom(path, lang="eng"):
            raise OSError("no such file")

        out, done, failed = mod.process_note("![[x.png]]", boom, "eng", 5)
        assert (done, failed) == (1, 1)
        assert "(unreadable)" in out

    def test_max_images_limit(self):
        out, done, _ = mod.process_note(
            self.CONTENT, lambda p, lang="eng": "t", "eng", max_images=1
        )
        assert done == 1 and out.count(mod.OCR_START) == 1

    def test_no_images_untouched(self):
        original = "plain note"
        out, done, failed = mod.process_note(original, lambda p, lang="eng": "t", "eng", 5)
        assert out == original and (done, failed) == (0, 0)


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


@pytest.fixture()
def ocr_bridge(bind_client, fake_bridge, monkeypatch):
    monkeypatch.setattr(mod, "HAS_OCR", True, raising=False)
    fake_bridge.get_active_note_absolute_path.return_value = "/vault/n.md"
    fake_bridge.get_current_vault_absolute_path.return_value = "/vault"
    return fake_bridge


class TestRun:
    def test_happy_path_writes_transcriptions_with_vault_paths(self, ocr_bridge, monkeypatch):
        seen_paths = []

        def fake_default(abs_path, lang="eng"):
            seen_paths.append((abs_path, lang))
            return "recognised!"

        monkeypatch.setattr(mod, "_default_transcribe", fake_default)
        ocr_bridge.get_active_note_content.return_value = "![[img/scan.png]]"

        mod.run(ocr_bridge)

        written = ocr_bridge.modify_note_content.call_args[0][1]
        assert "> recognised!" in written
        assert seen_paths == [("/vault/img/scan.png", "eng")]

    def test_language_setting_forwarded(self, ocr_bridge, monkeypatch):
        ocr_bridge.get_script_settings.return_value = {"language": "fra"}
        seen_langs = []
        monkeypatch.setattr(
            mod, "_default_transcribe", lambda p, lang="eng": seen_langs.append(lang) or "ok"
        )
        ocr_bridge.get_active_note_content.return_value = "![[a.png]]"

        mod.run(ocr_bridge)

        assert seen_langs == ["fra"]

    def test_no_images_notifies_only(self, ocr_bridge):
        ocr_bridge.get_active_note_content.return_value = "text only"

        mod.run(ocr_bridge)

        ocr_bridge.modify_note_content.assert_not_called()

    def test_missing_deps_hint(self, bind_client, fake_bridge, monkeypatch):
        bind_client(mod)
        monkeypatch.setattr(mod, "HAS_OCR", False, raising=False)
        fake_bridge.get_active_note_content.return_value = "![[a.png]]"

        mod.run(fake_bridge)

        assert any(
            "pip install pytesseract" in str(c.args[0])
            for c in fake_bridge.show_notification.call_args_list
        )
