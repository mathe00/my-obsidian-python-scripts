"""Unit tests for isbn-book-card.py."""

from typing import ClassVar

import pytest
from conftest import load_script

mod = load_script("isbn-book-card.py")


# ---------------------------------------------------------------------------
# ISBN normalisation & checksums (hand-rolled algorithms)
# ---------------------------------------------------------------------------


class TestIsbnValidation:
    def test_normalise_strips_separators(self):
        assert mod.normalise_isbn("978-0 306 40615-7") == "9780306406157"
        assert mod.normalise_isbn("0-306-40615-2") == "0306406152"

    @pytest.mark.parametrize(
        ("isbn", "expected"),
        [
            ("048665088X", True),  # classic ISBN-10 with check char X
            ("0306406152", True),  # valid ISBN-10
            ("9780306406157", True),  # canonical valid ISBN-13
            ("9780306406158", False),  # bad ISBN-13 check digit
            ("0306406151", False),  # bad ISBN-10 check digit
            ("12345", False),  # wrong length
            ("abcdefghijklm", False),  # garbage
        ],
    )
    def test_checksum_matrix(self, isbn, expected):
        assert mod.is_valid_isbn(isbn) is expected

    def test_lowercase_x_accepted(self):
        assert mod.is_valid_isbn(mod.normalise_isbn("048665088x")) is True


# ---------------------------------------------------------------------------
# payload parsing & merging
# ---------------------------------------------------------------------------

OL_PAYLOAD = {
    "ISBN:9780306406157": {
        "title": "It",
        "url": "https://openlibrary.org/b/x",
        "authors": [{"name": "Stephen King"}],
        "publish_date": "1986",
        "publishers": [{"name": "Viking"}],
        "cover": {"large": "https://ol/cover-L.jpg"},
    }
}

GB_PAYLOAD = {
    "items": [
        {
            "volumeInfo": {
                "title": "",
                "authors": [],
                "publishedDate": "1986-09",
                "imageLinks": {"thumbnail": "http://books.google/cover.jpg"},
            }
        }
    ]
}


class TestParsers:
    def test_openlibrary_full_extraction(self):
        card = mod.parse_openlibrary(OL_PAYLOAD, "9780306406157")
        assert card["title"] == "It"
        assert card["authors"] == ["Stephen King"]
        assert card["cover"] == "https://ol/cover-L.jpg"

    def test_openlibrary_empty_payload(self):
        card = mod.parse_openlibrary({}, "0000")
        assert card["title"] == "" and card["authors"] == []

    def test_googlebooks_fills_and_upgrades_http(self):
        filler = mod.parse_googlebooks(GB_PAYLOAD)
        assert filler["date"] == "1986-09"
        assert filler["cover"].startswith("https://")

    def test_merge_prefers_primary_keeps_filler_gaps(self):
        primary = {"title": "OL Title", "authors": ["A"], "date": "", "publisher": "", "cover": ""}
        filler = {
            "title": "GB Title",
            "authors": [],
            "date": "2000",
            "publisher": "Pub",
            "cover": "c.png",
        }
        merged = mod.merge_cards(primary, filler)
        assert merged["title"] == "OL Title"  # primary wins
        assert merged["date"] == "2000"  # gap filled
        assert merged["cover"] == "c.png"


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


class TestRenderCard:
    FULL_CARD: ClassVar[dict] = {
        "title": "It",
        "authors": ["Stephen King"],
        "date": "1986",
        "publisher": "Viking",
        "cover": "https://c/L.jpg",
        "url": "https://ol/b/x",
    }

    def test_full_card_sections(self):
        md = mod.render_card("9780306406157", self.FULL_CARD)
        assert md.startswith("---\ntitle:")
        assert "# It" in md and "**Author(s):** Stephen King" in md
        assert "![cover](https://c/L.jpg)" in md
        assert "[OpenLibrary page]" in md

    def test_minimal_card_degrades(self):
        md = mod.render_card(
            "000", {"title": "", "authors": [], "date": "", "publisher": "", "cover": "", "url": ""}
        )
        assert "# 000" in md and "Unknown author" in md
        assert "![cover]" not in md


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


@pytest.fixture()
def isbn_bridge(bind_client, fake_bridge, monkeypatch):
    monkeypatch.setattr(
        mod,
        "fetch_card",
        lambda isbn: {
            "title": "It",
            "authors": ["S. King"],
            "date": "1986",
            "publisher": "V",
            "cover": "c",
            "url": "",
        },
    )
    return fake_bridge


class TestRun:
    def test_valid_isbn_replaces_selection(self, isbn_bridge):
        isbn_bridge.get_selected_text.return_value = "978-0-306-40615-7"

        mod.run(isbn_bridge)

        inserted = isbn_bridge.replace_selected_text.call_args[0][0]
        assert "# It" in inserted and "'9780306406157'" in inserted

    def test_invalid_checksum_notifies_only(self, bind_client, fake_bridge, monkeypatch):
        bind_client(mod)
        called = False

        def _should_not_run(isbn):
            nonlocal called
            called = True
            return {}

        monkeypatch.setattr(mod, "fetch_card", _should_not_run)
        fake_bridge.get_selected_text.return_value = "9780306406158"

        mod.run(fake_bridge)

        assert called is False
        fake_bridge.replace_selected_text.assert_not_called()

    def test_unknown_book_notifies_and_does_not_insert(self, bind_client, fake_bridge, monkeypatch):
        bind_client(mod)
        fake_bridge.get_selected_text.return_value = "9780306406157"
        monkeypatch.setattr(
            mod,
            "fetch_card",
            lambda isbn: {
                "title": "",
                "authors": [],
                "date": "",
                "publisher": "",
                "cover": "",
                "url": "",
            },
        )

        mod.run(fake_bridge)

        fake_bridge.replace_selected_text.assert_not_called()
        assert any(
            "No metadata" in str(c.args[0]) for c in fake_bridge.show_notification.call_args_list
        )

    def test_empty_selection_notifies(self, isbn_bridge):
        isbn_bridge.get_selected_text.return_value = ""

        mod.run(isbn_bridge)

        isbn_bridge.replace_selected_text.assert_not_called()
