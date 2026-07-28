"""Regression tests for the 2026-07-28 chapter scope guard.

Chapter selection scored `len(term_tokens & title_tokens)` — how much of the QUERY a chapter
title covers — and never looked at what the TITLE adds. That is one-directional, so for the term
"vancomycin" the chapters *Vancomycin* and *Vancomycin-Resistant Enterococci* both scored 1 and
the tie fell to NCBI's relevance order. A dev-vs-main sweep measured ~8-10 of 55 imported
chapters as narrower or differently scoped than the question, and because a chapter carries
25-60k characters, the wrong one then dominates the entire prompt.

The guard is a TIE-BREAK, never a filter. `test_scope_guard_is_never_lossy` is the load-bearing
test: the rejecting variant of this idea was correct 8/8 on unit cases and recovered 0/7 on real
data, and was reverted (ledger 2026-07-28). Re-ranking cannot reduce coverage; rejection can.
"""
import pytest

from app.config import settings
from app.services.data_fetcher import _chapter_scope_extra, _STRUCTURAL_TITLE_TOKENS

pytestmark = pytest.mark.citation


@pytest.fixture
def guard_on(monkeypatch):
    monkeypatch.setattr(settings, "chapter_scope_guard_enabled", True)


# ── The measured real-world failures ──────────────────────────────────────────

@pytest.mark.parametrize("term,better,worse", [
    # (query, correctly-scoped chapter, the chapter actually imported on 2026-07-28)
    ("vancomycin",              "Vancomycin",              "Vancomycin-Resistant Enterococci"),
    ("preeclampsia",            "Preeclampsia",            "Ocular Manifestations of Preeclampsia"),
    ("sepsis",                  "Sepsis",                  "Laboratory Evaluation of Sepsis"),
    ("lumbar puncture",         "Lumbar Puncture",         "Fluoroscopy-Guided Lumbar Puncture"),
    ("myasthenia gravis",       "Myasthenia Gravis",       "Anesthesia for Patients With Myasthenia Gravis"),
    ("chest tube thoracostomy", "Chest Tube Thoracostomy", "Chest Tube Insertion in the Neonate"),
    ("urinary tract infection", "Urinary Tract Infection", "Urinary Tract Infection in Pregnancy"),
    ("chronic kidney disease",  "Chronic Kidney Disease",  "Chronic Kidney Disease-Mineral Bone Disorder"),
    ("status epilepticus",      "Status Epilepticus",      "New Onset Refractory Status Epilepticus"),
])
def test_correctly_scoped_chapter_scores_lower_extra(term, better, worse):
    """Lower `scope_extra` == better scoped. Every one of these is a measured production case."""
    assert _chapter_scope_extra(term, better) < _chapter_scope_extra(term, worse), (
        f"{better!r} should out-rank {worse!r} for query {term!r}")


def test_exact_title_match_has_zero_extra():
    assert _chapter_scope_extra("pericardiocentesis", "Pericardiocentesis") == 0
    assert _chapter_scope_extra("diabetic ketoacidosis", "Diabetic Ketoacidosis") == 0


# ── Cases that must NOT be penalised into oblivion ────────────────────────────

def test_structural_words_are_not_counted_as_qualifiers():
    """"of"/"the"/"with" carry no clinical scope, so they must never look like added scope."""
    assert _chapter_scope_extra("hyponatremia", "Hyponatremia") == \
           _chapter_scope_extra("hyponatremia", "The Hyponatremia")


def test_population_words_ARE_counted_as_qualifiers():
    """The opposite of the above, and the reason `_GENERIC_TITLE_TOKENS` is NOT reused here:
    it contains adult/child/infant, but a population qualifier is exactly the scope shift this
    guard exists to catch — a neonatal chest-tube chapter is the wrong answer for an adult."""
    assert "neonate" not in _STRUCTURAL_TITLE_TOKENS
    assert "child" not in _STRUCTURAL_TITLE_TOKENS
    assert _chapter_scope_extra("chest tube", "Chest Tube Insertion in the Neonate") > 0
    assert _chapter_scope_extra("bronchiolitis", "Bronchiolitis in Children") > 0


def test_abbreviation_expansion_is_not_a_false_positive_when_it_is_the_only_option():
    """"SGLT2 inhibitors" -> "Sodium-Glucose Transport 2 (SGLT2) Inhibitors" IS the right chapter.

    The guard scores it as adding qualifiers, which is why it must stay a TIE-BREAK: with no
    better-scoped rival in the candidate set, the expansion still wins by being the only one
    left. This test pins the score as non-zero so the behaviour is understood rather than
    accidental — the safety comes from `test_scope_guard_is_never_lossy`, not from this score.
    """
    assert _chapter_scope_extra(
        "SGLT2 inhibitors", "Sodium-Glucose Transport 2 (SGLT2) Inhibitors") > 0


def test_candidate_diagnosis_chapter_is_scored_against_its_own_term():
    """Candidate chapters are fetched with the CANDIDATE as the search term, so
    "Acute Pulmonary Embolism" is scored against "pulmonary embolism" — not against the
    original vignette ("pleuritic chest pain"), which would wrongly look like scope drift.

    Asserted as a COMPARISON, not an absolute bound: the absolute number moves whenever the
    weighting changes (it did — "acute" is a narrowing token worth 2), and a bound that has to
    be relaxed to stay green is testing the constant rather than the behaviour.
    """
    against_own_term = _chapter_scope_extra("pulmonary embolism", "Acute Pulmonary Embolism")
    against_vignette = _chapter_scope_extra("pleuritic chest pain", "Acute Pulmonary Embolism")
    assert against_own_term < against_vignette, (
        "a candidate chapter must be judged against the candidate diagnosis it was searched "
        "with, not against the symptom vignette")
    assert _chapter_scope_extra("delirium", "Differentiating Delirium Versus Dementia in Older Adults") > 1


# ── Ordering behaviour ────────────────────────────────────────────────────────

def _pick(term, titles, guard):
    """Mirror of the sort key in `_fetch_book_monographs_live`, same candidate set both ways."""
    scored = []
    for rank, t in enumerate(titles):
        import re
        tt = set(re.findall(r"[a-z0-9]+", t.lower()))
        qt = set(re.findall(r"[a-z0-9]+", term.lower()))
        scored.append((len(qt & tt), rank, t))
    if guard:
        scored.sort(key=lambda x: (-x[0], _chapter_scope_extra(term, x[2]), x[1]))
    else:
        scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][2]


def test_guard_changes_the_winner_on_the_measured_case():
    """NCBI returned the qualified chapter FIRST — that ordering is the whole bug."""
    titles = ["Vancomycin-Resistant Enterococci", "Vancomycin", "Vancomycin Infusion Reaction"]
    assert _pick("vancomycin", titles, guard=False) == "Vancomycin-Resistant Enterococci"
    assert _pick("vancomycin", titles, guard=True) == "Vancomycin"


def test_narrowing_qualifier_outweighs_a_longer_elaboration():
    """A different population/side/acuity is a different clinical entity, not an elaboration.

    Found by the CONTROL arm of the live A/B (2026-07-28): a raw token count made
    "Right Heart Failure" (1 extra token) beat "Heart Failure and Ejection Fraction" (2), but
    right heart failure is cor pulmonale — a distinct entity — while ejection fraction is heart
    failure's primary classification axis. Narrowing tokens are therefore weighted x2.
    """
    titles = ["Heart Failure and Ejection Fraction", "Right Heart Failure"]
    assert _pick("heart failure", titles, guard=True) == "Heart Failure and Ejection Fraction"
    assert _chapter_scope_extra("heart failure", "Right Heart Failure") >= \
           _chapter_scope_extra("heart failure", "Heart Failure and Ejection Fraction")


def test_query_own_tokens_are_never_penalised():
    """"acute" in the QUERY must not be scored as scope the chapter added."""
    assert _chapter_scope_extra("acute pancreatitis", "Acute Pancreatitis") == 0
    assert _chapter_scope_extra("chronic kidney disease", "Chronic Kidney Disease") == 0


def test_guard_never_beats_a_higher_overlap_chapter():
    """Scope is only a TIE-BREAK: a chapter matching more of the query still wins outright,
    even though its longer title necessarily carries more tokens."""
    titles = ["Puncture", "Fluoroscopy-Guided Lumbar Puncture"]
    assert _pick("lumbar puncture", titles, guard=True) == "Fluoroscopy-Guided Lumbar Puncture"


def test_scope_guard_is_never_lossy():
    """THE load-bearing property: the guard re-orders a candidate set, it never shrinks one.

    The rejecting variant of this idea was reverted on 2026-07-28 (8/8 on unit cases, 0/7 on
    real data — the unqualified chapters simply do not exist). So when the only candidate is a
    qualified chapter, it must still be returned.
    """
    only_qualified = ["Ocular Manifestations of Preeclampsia"]
    assert _pick("preeclampsia", only_qualified, guard=True) == only_qualified[0]

    for term, titles in [
        ("vancomycin", ["Vancomycin-Resistant Enterococci", "Vancomycin"]),
        ("sepsis", ["Laboratory Evaluation of Sepsis", "Sepsis", "Neonatal Sepsis"]),
        ("chest tube", ["Chest Tube Insertion in the Neonate"]),
    ]:
        on = {_pick(term, titles, guard=True)}
        off = {_pick(term, titles, guard=False)}
        assert len(on) == len(off) == 1, "a pick must always be produced"
        assert on <= set(titles), "the guard must never invent a chapter"


def test_flag_off_is_byte_identical_to_previous_behaviour():
    """Prod defaults to False, so the OFF path must be exactly the old sort — overlap, then
    NCBI relevance rank, with no scope term anywhere in the key."""
    titles = ["Laboratory Evaluation of Sepsis", "Sepsis"]
    assert _pick("sepsis", titles, guard=False) == "Laboratory Evaluation of Sepsis"
    assert settings.chapter_scope_guard_enabled is False, "prod default must stay OFF"
