"""Unit tests for semantic-similar-notes.py (stdlib TF-IDF engine)."""

from typing import ClassVar

import pytest
from conftest import load_script

mod = load_script("semantic-similar-notes.py")


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------


class TestTokenize:
    def test_lowercase_and_split(self):
        assert mod.tokenize("Hello World of Python") == ["hello", "world", "python"]

    def test_stopwords_removed(self):
        assert mod.tokenize("the cat and the hat") == ["cat", "hat"]

    def test_short_tokens_dropped(self):
        assert mod.tokenize("to be or not") == ["not"]

    def test_accents_stripped(self):
        assert mod.tokenize("Café CRÈME") == ["cafe", "creme"]

    def test_digits_kept(self):
        assert mod.tokenize("python 313 rocks") == ["python", "313", "rocks"]

    def test_empty(self):
        assert mod.tokenize("") == []


# ---------------------------------------------------------------------------
# TF-IDF + cosine
# ---------------------------------------------------------------------------


class TestTfidf:
    CORPUS: ClassVar[dict] = {
        "Python Tips": "python python lists comprehension tricks",
        "JS Tips": "javascript closures promises tricks",
        "Mixed": "python javascript interop",
    }

    def test_all_vectors_l2_normalised(self):
        vectors = mod.build_tfidf(self.CORPUS)
        for name, vec in vectors.items():
            norm = sum(w * w for w in vec.values()) ** 0.5
            assert norm == pytest.approx(1.0), f"vector {name} not normalised"

    def test_repeated_term_gets_weight(self):
        vectors = mod.build_tfidf(self.CORPUS)
        # 'python' appears twice in Python Tips -> its weight beats single-occurrence terms there.
        py_vec = vectors["Python Tips"]
        assert py_vec["python"] > py_vec["lists"]

    def test_rare_terms_score_higher_than_common(self):
        vectors = mod.build_tfidf(self.CORPUS)
        # 'tricks' is in 2/3 docs, 'closures' only in 1 -> idf boosts closures in JS Tips.
        js_vec = vectors["JS Tips"]
        assert js_vec["closures"] > js_vec["tricks"]

    def test_empty_doc_gives_empty_vector(self):
        vectors = mod.build_tfidf({"Empty": "", "Full": "words here"})
        assert vectors["Empty"] == {}


class TestCosine:
    def test_identical_vectors(self):
        # Properly L2-normalised vector.
        v = {"a": 1 / 2**0.5, "b": 1 / 2**0.5}
        assert mod.cosine(v, dict(v)) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert mod.cosine({"a": 1.0}, {"b": 1.0}) == pytest.approx(0.0)

    def test_empty_vector_is_zero(self):
        assert mod.cosine({"a": 1.0}, {}) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# suggest_related
# ---------------------------------------------------------------------------

VECTORS = {
    "Active": {"python": 0.8, "testing": 0.6},
    "PyFriend": {"python": 0.9, "pytest": 0.4},  # high overlap
    "Unrelated": {"gardening": 1.0},
    "LinkedAlready": {"python": 0.5, "testing": 0.5},
}


class TestSuggestRelated:
    def test_excludes_self_and_linked_and_low_scores(self):
        result = mod.suggest_related("Active", VECTORS, {"LinkedAlready"}, top_k=10, min_score=0.01)
        names = [n for n, _ in result]
        assert "Active" not in names
        assert "LinkedAlready" not in names
        assert "Unrelated" not in names  # cosine 0 < min_score
        assert names == ["PyFriend"]

    def test_sorted_descending_and_topk_respected(self):
        big = {f"N{i}": {"shared": 1.0 - i / 20} for i in range(10)}
        big["Seed"] = {"shared": 1.0}
        result = mod.suggest_related("Seed", big, set(), top_k=3, min_score=0.01)
        assert len(result) == 3
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Section rendering & idempotent upsert
# ---------------------------------------------------------------------------


class TestUpsertSection:
    def test_appends_when_absent(self):
        out = mod.upsert_section("# Note", mod.render_section([("Other", 0.42)]))
        assert out.count(mod.SECTION_START) == 1
        assert "[[Other]]" in out

    def test_replaces_previous_block(self):
        first = mod.upsert_section("# Note", mod.render_section([("Old", 0.1)]))
        second = mod.upsert_section(first, mod.render_section([("New", 0.9)]))
        assert second.count(mod.SECTION_START) == 1
        assert "[[Old]]" not in second
        assert "[[New]]" in second


# ---------------------------------------------------------------------------
# run() orchestration with fake bridge
# ---------------------------------------------------------------------------


@pytest.fixture()
def sem_bridge(bind_client, fake_bridge):
    return bind_client(mod)


class TestRun:
    def _configure(self, bridge):
        bridge.get_active_note_relative_path.return_value = "notes/A.md"
        bridge.get_active_note_absolute_path.return_value = "/vault/notes/A.md"
        bridge.get_all_note_paths.return_value = ["notes/A.md", "notes/B.md", "notes/C.md"]
        bridge.get_note_content.side_effect = lambda p: {
            "notes/A.md": "quantum physics basics",
            "notes/B.md": "quantum physics advanced topics",
            "notes/C.md": "cooking pasta recipes",
        }[p]
        bridge.get_links.return_value = []
        bridge.get_active_note_content.return_value = "# A\nquantum physics basics"

    def test_suggestions_found_and_section_written(self, sem_bridge):
        self._configure(sem_bridge)
        mod.run(sem_bridge)

        written = sem_bridge.modify_note_content.call_args[0][1]
        assert "[[B]]" in written  # B overlaps A strongly
        assert "[[C]]" not in written  # C has zero overlap

    def test_append_disabled_skips_write(self, sem_bridge):
        self._configure(sem_bridge)
        sem_bridge.get_script_settings.return_value = {"append_section": False}

        mod.run(sem_bridge)

        sem_bridge.modify_note_content.assert_not_called()

    def test_single_note_vault_bails_out(self, sem_bridge):
        sem_bridge.get_active_note_relative_path.return_value = "only.md"
        sem_bridge.get_all_note_paths.return_value = ["only.md"]

        mod.run(sem_bridge)

        sem_bridge.modify_note_content.assert_not_called()
