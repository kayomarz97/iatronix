import pytest
from app.services.article_registry import (
    build_article_registry, pubmed_url, clinicaltrials_url, doi_url,
    ncbi_books_url, semantic_scholar_url,
)


class _Obj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_pubmed_url_only_digits():
    assert pubmed_url("12345") == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert pubmed_url("abc") is None
    assert pubmed_url("") is None


def test_nct_url_format():
    assert clinicaltrials_url("NCT01234567") == "https://clinicaltrials.gov/study/NCT01234567"
    assert clinicaltrials_url("NCT123") is None


def test_doi_url():
    assert doi_url("10.1056/NEJMoa1234").startswith("https://doi.org/10.1056/")
    assert doi_url("not-a-doi") is None


def test_ncbi_books_url():
    assert ncbi_books_url("NBK279097") == "https://www.ncbi.nlm.nih.gov/books/NBK279097/"
    assert ncbi_books_url("279097") is None


def test_semantic_scholar_url():
    assert semantic_scholar_url("abc123def").startswith("https://www.semanticscholar.org/paper/")


def test_registry_dedup_and_url_required():
    fetched = _Obj(
        drug_data=_Obj(
            guideline_abstracts=[
                {"title": "Foo", "pmid": "111"},
                {"title": "Foo", "pmid": "111"},  # dup
                {"title": "Untitled", "pmid": ""},  # no URL → excluded
            ],
            systematic_review_abstracts=[],
            clinical_trial_abstracts=[],
            label_url=None,
            brand_name=None,
            generic_name=None,
        ),
        disease_data=None, condition_data=None, procedure_data=None,
        evidence_data=None, comparative_evidence=None,
        comorbidity_data=[], comparative_drug_data=[],
    )
    reg = build_article_registry(fetched)
    assert len(reg.items) == 1
    assert reg.items[0].url == "https://pubmed.ncbi.nlm.nih.gov/111/"
    assert reg.by_pmid["111"].ref_token == "REF_1"


def test_to_reference_list_groups_cited_first():
    fetched = _Obj(
        drug_data=_Obj(
            guideline_abstracts=[{"title": "A", "pmid": "1"}, {"title": "B", "pmid": "2"}],
            systematic_review_abstracts=[], clinical_trial_abstracts=[],
            label_url=None, brand_name=None, generic_name=None,
        ),
        disease_data=None, condition_data=None, procedure_data=None,
        evidence_data=None, comparative_evidence=None,
        comorbidity_data=[], comparative_drug_data=[],
    )
    reg = build_article_registry(fetched)
    reg.items[1].used_inline = True
    out = reg.to_reference_list()
    assert out[0]["title"] == "B"
    assert out[0]["used_inline"] is True
    assert out[1]["used_inline"] is False


def test_best_match_jaccard_threshold():
    fetched = _Obj(
        drug_data=_Obj(
            guideline_abstracts=[
                {"title": "Metformin in type 2 diabetes mellitus", "pmid": "5001"},
            ],
            systematic_review_abstracts=[], clinical_trial_abstracts=[],
            label_url=None, brand_name=None, generic_name=None,
        ),
        disease_data=None, condition_data=None, procedure_data=None,
        evidence_data=None, comparative_evidence=None,
        comorbidity_data=[], comparative_drug_data=[],
    )
    reg = build_article_registry(fetched)
    hit = reg.best_match("metformin first-line therapy for diabetes mellitus")
    assert hit is not None
    miss = reg.best_match("the patient ate breakfast at noon")
    assert miss is None
