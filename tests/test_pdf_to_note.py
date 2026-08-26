"""Unit tests for pdf-to-note.py (PdfReader injected — pypdf never required)."""

import pytest
from conftest import load_script

mod = load_script("pdf-to-note.py")


# ---------------------------------------------------------------------------
# link discovery
# ---------------------------------------------------------------------------


class TestFindPdfLinks:
    def test_wikilink_and_markdown_both_caught(self):
        content = "see [[a.pdf]] and [b](docs/b.PDF)"
        assert mod.find_pdf_links(content) == ["a.pdf", "docs/b.PDF"]

    def test_duplicates_deduped_order_kept(self):
        assert mod.find_pdf_links("[[x.pdf]] [[x.pdf]] [y](y.pdf)") == ["x.pdf", "y.pdf"]

    def test_non_pdf_ignored(self):
        assert mod.find_pdf_links("[[image.png]] [page](note.md)") == []


# ---------------------------------------------------------------------------
# heading heuristic & rendering
# ---------------------------------------------------------------------------


class TestHeadingsAndRender:
    def test_caps_line_promoted(self):
        text = "intro\nCHAPTER ONE\ndetails."
        out = mod.apply_heading_heuristic(text, enabled=True)
        assert "## Chapter One" in out
        assert "details." in out  # ends with '.' -> not promoted

    def test_disabled_keeps_verbatim(self):
        out = mod.apply_heading_heuristic("CHAPTER ONE", enabled=False)
        assert "##" not in out

    def test_render_note_structure(
        self,
    ):
        md = mod.render_extracted_note(
            "Docs/Doc.pdf", ["first page", "INTRO\nbody"], headings_enabled=True
        )
        assert 'source_pdf: "[[Doc.pdf]]"' in md
        assert "# Doc" in md
        assert "### Page 1" in md and "first page" in md
        assert "## Intro" in md  # heading detection applied inside pages

    def test_sibling_path(self):
        assert mod.sibling_note_path("a/b/Doc.pdf") == os.path.join("a", "b", "Doc (Extracted).md")

    def test_unique_target_suffixing(self, fake_bridge):
        fake_bridge.check_path_exists.side_effect = lambda p: p == "X.md"
        assert mod.unique_target(fake_bridge, "X.md").endswith("X (2).md")


import os  # noqa: E402 - used above; kept close to tests for readability

# ---------------------------------------------------------------------------
# extraction with injected reader
# ---------------------------------------------------------------------------


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakeReader:
    def __init__(self, path):
        assert path.endswith(".pdf")
        self.pages = [FakePage("alpha"), FakePage("")]


class TestExtractPages:
    def test_pages_extracted_via_injected_reader(self, monkeypatch):
        monkeypatch.setattr(mod, "PdfReader", FakeReader)
        pages = mod.extract_pages("/any/where.pdf")
        assert pages == ["alpha", ""]


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


@pytest.fixture()
def pdf_bridge(bind_client, fake_bridge, monkeypatch):
    monkeypatch.setattr(mod, "HAS_PYPDF", True, raising=False)
    monkeypatch.setattr(mod, "PdfReader", FakeReader)
    fake_bridge.get_current_vault_absolute_path.return_value = "/vault"
    fake_bridge.check_path_exists.return_value = False
    return fake_bridge


class TestRun:
    def test_creates_extracted_note(self, pdf_bridge):
        pdf_bridge.get_active_note_content.return_value = "read [[Docs/Doc.pdf]] now"

        mod.run(pdf_bridge)

        args, _ = pdf_bridge.create_note.call_args
        target, note_md = args[0], args[1]
        assert target == os.path.join("Docs", "Doc (Extracted).md")
        assert "### Page 1" in note_md and "alpha" in note_md

    def test_no_links_notifies_only(self, pdf_bridge):
        pdf_bridge.get_active_note_content.return_value = "just text"

        mod.run(pdf_bridge)

        pdf_bridge.create_note.assert_not_called()

    def test_missing_dep_hints(self, bind_client, fake_bridge, monkeypatch):
        bind_client(mod)
        monkeypatch.setattr(mod, "HAS_PYPDF", False, raising=False)
        monkeypatch.setattr(mod, "PdfReader", None)
        fake_bridge.get_active_note_content.return_value = "[[x.pdf]]"

        mod.run(fake_bridge)

        assert any(
            "pip install pypdf" in str(c.args[0])
            for c in fake_bridge.show_notification.call_args_list
        )
