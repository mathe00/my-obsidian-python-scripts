"""Unit tests for define_word_en_concise.py."""

import pytest
from conftest import load_script

mod = load_script("define_word_en_concise.py")


# ---------------------------------------------------------------------------
# truncate
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_text_unchanged(self):
        assert mod.truncate("short", 400) == "short"

    def test_long_text_truncated_with_ellipsis(self):
        result = mod.truncate("x" * 500)
        assert len(result) == mod.DEFINITION_MAX_LENGTH + 3
        assert result.endswith("...")

    def test_exact_limit_not_truncated(self):
        assert mod.truncate("y" * 400) == "y" * 400

    def test_custom_limit(self):
        assert mod.truncate("abcdef", 3) == "abc..."


# ---------------------------------------------------------------------------
# fetch_definition — network layer mocked via requests.get
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class TestFetchDefinition:
    def _patch_get(self, monkeypatch, response):
        captured = {}

        def fake_get(url, timeout=None):
            captured["url"] = url
            captured["timeout"] = timeout
            return response

        monkeypatch.setattr("requests.get", fake_get)
        return captured

    def test_success_returns_first_definition(self, monkeypatch):
        payload = [
            {
                "meanings": [
                    {
                        "definitions": [
                            {"definition": "The faculty of making fortunate discoveries."}
                        ]
                    }
                ]
            }
        ]
        captured = self._patch_get(monkeypatch, FakeResponse(200, payload))

        result = mod.fetch_definition("Serendipity")

        assert result == "The faculty of making fortunate discoveries."
        # Word is lowercased in the URL, timeout forwarded.
        assert captured["url"].endswith("/serendipity")
        assert captured["timeout"] == mod.API_TIMEOUT_SECONDS

    def test_non_200_returns_friendly_message(self, monkeypatch):
        self._patch_get(monkeypatch, FakeResponse(404))
        assert mod.fetch_definition("zzzqqq") == "'zzzqqq' not found or API error."

    def test_missing_meanings_falls_back(self, monkeypatch):
        self._patch_get(monkeypatch, FakeResponse(200, [{}]))
        assert mod.fetch_definition("odd") == "Definition format unclear."

    def test_empty_meanings_list_falls_back(self, monkeypatch):
        self._patch_get(monkeypatch, FakeResponse(200, [{"meanings": []}]))
        assert mod.fetch_definition("odd") == "Definition format unclear."

    def test_network_error_propagates(self, monkeypatch):
        import requests

        def boom(url, timeout=None):
            raise requests.exceptions.Timeout("too slow")

        monkeypatch.setattr("requests.get", boom)

        with pytest.raises(requests.exceptions.Timeout):
            mod.fetch_definition("word")


# ---------------------------------------------------------------------------
# main() — bridge orchestration against fake client
# ---------------------------------------------------------------------------


@pytest.fixture()
def word_bridge(bind_client, fake_bridge):
    return bind_client(mod)


class TestMain:
    def test_selection_produces_notification_with_word(self, word_bridge, monkeypatch):
        word_bridge.get_selected_text.return_value = "  Serendipity  "
        monkeypatch.setattr(
            "requests.get",
            lambda url, timeout=None: FakeResponse(
                200,
                [
                    {
                        "meanings": [
                            {
                                "definitions": [
                                    {"definition": "The faculty of making fortunate discoveries."}
                                ]
                            }
                        ]
                    }
                ],
            ),
        )

        mod.main()

        content = word_bridge.show_notification.call_args[0][0]
        assert content.startswith("**Serendipity:**")
        assert "fortunate discoveries" in content

    def test_url_is_lowercased_from_selection(self, word_bridge, monkeypatch):
        word_bridge.get_selected_text.return_value = "MiXeDCaSe"
        seen_urls = []

        def fake_get(url, timeout=None):
            seen_urls.append(url)
            return FakeResponse(200, [{"meanings": [{"definitions": [{"definition": "d"}]}]}])

        monkeypatch.setattr("requests.get", fake_get)
        mod.main()

        assert seen_urls and seen_urls[0].endswith("/mixedcase")

    def test_empty_selection_exits_silently(self, word_bridge):
        word_bridge.get_selected_text.return_value = ""

        with pytest.raises(SystemExit) as excinfo:
            mod.main()

        assert excinfo.value.code == 0
        word_bridge.show_notification.assert_not_called()

    def test_whitespace_only_selection_exits_silently(self, word_bridge):
        word_bridge.get_selected_text.return_value = "   \n\t "

        with pytest.raises(SystemExit):
            mod.main()

        word_bridge.show_notification.assert_not_called()

    def test_long_definition_truncated_in_notification(self, word_bridge, monkeypatch):
        word_bridge.get_selected_text.return_value = "longword"
        monkeypatch.setattr(
            "requests.get",
            lambda url, timeout=None: FakeResponse(
                200, [{"meanings": [{"definitions": [{"definition": "z" * 900}]}]}]
            ),
        )

        mod.main()

        content = word_bridge.show_notification.call_args[0][0]
        assert content.count("z") == mod.DEFINITION_MAX_LENGTH
        assert content.endswith("...")
