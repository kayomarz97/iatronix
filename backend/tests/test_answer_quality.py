"""Answer-quality eval tests (Phase 5d): sycophancy + uncited-claim detection."""

from app.services.answer_quality import (
    check_answer,
    find_sycophantic_phrases,
    find_uncited_claims,
    is_sycophantic,
)


def test_sycophancy_detected():
    assert is_sycophantic("Great question! As an expert, I'd recommend...")
    assert find_sycophantic_phrases("It is generally believed that, arguably, this helps")
    # clean, grounded clinical prose passes
    assert find_sycophantic_phrases(
        "Metformin is first-line for T2DM per ADA 2024 (LOE I)."
    ) == []


def test_uncited_claims_flagged_but_expert_opinion_ok():
    response = {
        "sections": [
            {"content_items": [
                {"value": "Statins reduce CV events", "source": "PMID 12345"},
                {"value": "Aspirin helps everyone", "source": ""},          # uncited -> flagged
                {"value": "Low-confidence note", "source": "Expert opinion"},  # demoted but OK
                {"value": "Unresolved", "source": "__UNRESOLVED_TOKEN__"},   # sentinel -> flagged
            ]},
        ],
    }
    uncited = find_uncited_claims(response)
    assert "Aspirin helps everyone" in uncited
    assert "Unresolved" in uncited
    assert "Statins reduce CV events" not in uncited
    assert "Low-confidence note" not in uncited


def test_check_answer_combined_pass_and_fail():
    good = {
        "bluf": {"headline": "Rivaroxaban dosing in AF", "body": "Per guidelines, 20 mg daily."},
        "sections": [{"content_items": [{"value": "20 mg OD", "source": "NICE NG196"}]}],
    }
    res = check_answer(good)
    assert res["sycophancy"] == [] and res["uncited"] == []

    bad = {
        "bluf": {"headline": "Great question!", "body": "I hope this helps."},
        "sections": [{"content_items": [{"value": "trust me", "source": ""}]}],
    }
    res2 = check_answer(bad)
    assert res2["sycophancy"]      # flattery flagged
    assert res2["uncited"]          # uncited claim flagged
