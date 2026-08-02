"""Regression tests for the reference PUBLICATION gate (2026-08-02).

Defect it pins: after the relevance floor and topicality gate have both run, ~1 in 5 published
references is still not about the question, because both existing valves FAIL OPEN (the
topicality gate steps aside when nothing matches; the floor re-admits up to min_keep) and
because several registry-feeding containers are never filtered at all. Measured over 48 queries
in test/results/CITATION_RELEVANCE_2026-08-02.md.

The gate governs PUBLICATION only. Two properties make it safe, and both are locked here:
  * a CITED reference is never dropped, whatever it scores;
  * registry.items is never pruned, so grounding, backfill and title-rescue still see everything.
"""
import pytest

from app.config import settings
from app.services.article_registry import build_article_registry
from app.services.rag_pipeline import subject_anchor

pytestmark = pytest.mark.citation


class _Obj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _art(title, pmid, abstract=""):
    return {"title": title, "pmid": pmid, "abstract": abstract, "source": "J"}


ON_SUBJECT = _art("Labetalol for severe hypertension in pregnancy", "111")
MENTION_ONLY = _art("Management of the difficult airway", "222",
                    "Agents including labetalol may be used.")
OFF_SUBJECT = _art("EuroGuiDerm guideline for the treatment of acne", "333",
                   "Acne vulgaris treatment recommendations.")


def _fetched():
    """A drug+condition shape: the condition list is exactly the leak measured in the sweep."""
    return _Obj(
        drug_data=_Obj(guideline_abstracts=[ON_SUBJECT], systematic_review_abstracts=[],
                       clinical_trial_abstracts=[], book_monographs=[]),
        condition_data=_Obj(guideline_abstracts=[MENTION_ONLY, OFF_SUBJECT],
                            systematic_review_abstracts=[], book_monographs=[]),
    )


@pytest.fixture
def gate_on(monkeypatch):
    monkeypatch.setattr(settings, "reference_publication_gate_enabled", True)
    monkeypatch.setattr(settings, "reference_publication_min_score", 3.0)
    monkeypatch.setattr(settings, "citation_ref_tokens_enabled", True)
    # Chapters only enter the registry at all when this is on (article_registry._walk_books).
    # It is true on dev; without it a chapter assertion passes vacuously against an empty registry.
    monkeypatch.setattr(settings, "citation_integrity_fix_enabled", True)


@pytest.fixture
def gate_off(monkeypatch):
    monkeypatch.setattr(settings, "reference_publication_gate_enabled", False)
    monkeypatch.setattr(settings, "citation_ref_tokens_enabled", True)
    monkeypatch.setattr(settings, "citation_integrity_fix_enabled", True)


def _titles(refs):
    return {r["title"] for r in refs}


# ── flag-off path must be byte-identical ──────────────────────────────────────

def test_flag_off_publishes_everything(gate_off):
    reg = build_article_registry(_fetched(), subject_anchor=["labetalol"])
    assert len(_titles(reg.to_reference_list())) == 3
    assert all(r.publish_score == -1.0 for r in reg.items), "no scoring when the flag is off"


def test_flag_on_without_anchor_publishes_everything(gate_on):
    """No anchor => nothing to judge against => publish all, never blank a reference list."""
    reg = build_article_registry(_fetched(), subject_anchor=None)
    assert len(_titles(reg.to_reference_list())) == 3
    assert all(r.publish_score == -1.0 for r in reg.items)


# ── the gate itself ───────────────────────────────────────────────────────────

def test_uncited_off_subject_reference_is_not_published(gate_on):
    refs = _titles(build_article_registry(_fetched(), subject_anchor=["labetalol"])
                   .to_reference_list())
    assert ON_SUBJECT["title"] in refs
    assert OFF_SUBJECT["title"] not in refs, "the acne guideline must not be cited for labetalol"


def test_abstract_only_mention_is_grounding_only(gate_on):
    """Mention != aboutness. Scores 2.0 (abstract) < 3.0 (title), so it grounds but is unpublished."""
    reg = build_article_registry(_fetched(), subject_anchor=["labetalol"])
    by_title = {r.title: r for r in reg.items}
    assert by_title[MENTION_ONLY["title"]].publish_score == 2.0
    assert by_title[ON_SUBJECT["title"]].publish_score == 3.0
    assert MENTION_ONLY["title"] not in _titles(reg.to_reference_list())


def test_cited_reference_is_always_published_whatever_it_scores(gate_on):
    """THE safety property: the gate can never break a citation the answer relies on."""
    reg = build_article_registry(_fetched(), subject_anchor=["labetalol"])
    worst = next(r for r in reg.items if r.title == OFF_SUBJECT["title"])
    assert worst.publish_score == 0.0
    reg.mark_used(worst)
    assert OFF_SUBJECT["title"] in _titles(reg.to_reference_list())


def test_registry_items_are_never_pruned(gate_on):
    """Grounding, _backfill_from_registry and _title_rescue_pass all read registry.items.
    The gate must filter the OUTPUT of to_reference_list, never the registry itself."""
    reg = build_article_registry(_fetched(), subject_anchor=["labetalol"])
    assert len(reg.items) == 3
    assert len(reg.to_reference_list()) < len(reg.items)
    assert reg.lookup_id(pmid="333") is not None, "off-subject entry still resolvable by id"


def test_differential_chapters_survive_via_candidate_diagnoses(gate_on):
    """The measured false-positive class: on a ddx query the CORRECT references are the
    differentials, whose titles never contain the presenting complaint. Anchoring on the
    complaint alone would delete exactly what the ddx feature exists to retrieve."""
    fetched = _Obj(disease_data=_Obj(
        guideline_abstracts=[], systematic_review_abstracts=[], clinical_trial_abstracts=[],
        book_monographs=[{"title": "Acute Pulmonary Embolism", "nbk_id": "NBK560551"},
                         {"title": "Pericarditis", "nbk_id": "NBK431080"}]))
    complaint_only = build_article_registry(fetched, subject_anchor=["pleuritic chest pain"])
    assert len(complaint_only.items) == 2, "both chapters must be IN the registry to start with"
    assert all(r.publish_score == 0.0 for r in complaint_only.items), \
        "anchored on the complaint alone, both correct chapters score 0 — the failure mode"

    with_candidates = build_article_registry(
        fetched, subject_anchor=["pleuritic chest pain", "pulmonary embolism", "pericarditis"])
    assert all(r.publish_score == 3.0 for r in with_candidates.items), \
        "with the candidates in the anchor they are title matches, published on merit"
    assert len(_titles(with_candidates.to_reference_list())) == 2


# ── never-empty safeguard ─────────────────────────────────────────────────────

def test_gate_never_empties_a_non_empty_reference_list(gate_on, monkeypatch):
    """Measured 2026-08-02: the gate alone blanked 4 of 20 queries. A clinician reading an
    answer with NO references is a worse failure than one tangential reference."""
    monkeypatch.setattr(settings, "reference_publication_min_keep", 3)
    fetched = _Obj(condition_data=_Obj(
        guideline_abstracts=[OFF_SUBJECT, _art("Another unrelated paper", "444")],
        systematic_review_abstracts=[], book_monographs=[]))
    reg = build_article_registry(fetched, subject_anchor=["labetalol"])
    assert all(r.publish_score == 0.0 for r in reg.items), "nothing passes the gate here"
    assert len(reg.to_reference_list()) == 2, "falls back rather than publishing nothing"


def test_safeguard_is_bounded_by_min_keep(gate_on, monkeypatch):
    monkeypatch.setattr(settings, "reference_publication_min_keep", 1)
    fetched = _Obj(condition_data=_Obj(
        guideline_abstracts=[OFF_SUBJECT, _art("Another unrelated paper", "444"),
                             _art("A third unrelated paper", "555")],
        systematic_review_abstracts=[], book_monographs=[]))
    reg = build_article_registry(fetched, subject_anchor=["labetalol"])
    assert len(reg.to_reference_list()) == 1


def test_safeguard_never_fires_when_the_gate_is_off(gate_off):
    """It must key off "the gate judged and rejected everything", never off an empty list."""
    fetched = _Obj(condition_data=_Obj(guideline_abstracts=[OFF_SUBJECT],
                                       systematic_review_abstracts=[], book_monographs=[]))
    reg = build_article_registry(fetched, subject_anchor=["labetalol"])
    assert len(reg.to_reference_list()) == 1
    assert reg.items[0].publish_score == -1.0


def test_alphanumeric_class_names_are_not_rejected(gate_on):
    """The measured false negative: exact-substring scoring rejected a perfect chapter match.
    'SGLT2 inhibitors' vs 'Sodium-Glucose Transport 2 (SGLT2) Inhibitors' must be a TITLE hit."""
    fetched = _Obj(evidence_data=_Obj(
        guideline_abstracts=[], systematic_review_abstracts=[], clinical_trial_abstracts=[],
        book_monographs=[{"title": "Sodium-Glucose Transport 2 (SGLT2) Inhibitors",
                          "nbk_id": "NBK576405"}]))
    reg = build_article_registry(fetched, subject_anchor=["SGLT2 inhibitors"])
    assert reg.items[0].publish_score == 3.0


# ── subject_anchor: one source of truth for floor, gate and publication ───────

def test_anchor_prefers_resolved_drug_name():
    fetched = _Obj(drug_data=_Obj(generic_name="labetalol", brand_name="TRANDATE"))
    assert subject_anchor(fetched, ["labetalol", "pregnancy"], "drug") == [
        "labetalol", "TRANDATE", "labetalol"]


def test_anchor_keeps_all_entities_for_comparative():
    assert subject_anchor(None, ["apixaban", "warfarin"], "comparative") == ["apixaban", "warfarin"]


def test_anchor_uses_first_entity_when_no_drug():
    assert subject_anchor(None, ["sepsis", "lactate"], "disease") == ["sepsis"]


def test_anchor_appends_candidate_diagnoses():
    got = subject_anchor(None, ["hyponatremia"], "disease", candidate_diagnoses=["SIADH", " ", None])
    assert got == ["hyponatremia", "SIADH"]


def test_anchor_handles_empty_entities():
    assert subject_anchor(None, None, "disease") == []
