"""Evidence ranking for the medical retrieval pipeline.

Scores article dicts by study type, relevance, recency, full-text
availability, and citation count. Penalizes animal-only and
off-population studies. Called after data fetch, before LLM synthesis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_CURRENT_YEAR: int = datetime.now().year

# Drug/term synonym groups for relevance matching (INN ⇄ US names, common variants).
# Used only when relevance_synonyms is on, so the floor doesn't drop a legit article that
# uses the other name (e.g. "acetaminophen" for a "paracetamol" query).
_SYNONYM_GROUPS: list[set[str]] = [
    {"paracetamol", "acetaminophen"},
    {"adrenaline", "epinephrine"},
    {"noradrenaline", "norepinephrine"},
    {"salbutamol", "albuterol"},
    {"frusemide", "furosemide"},
    {"lignocaine", "lidocaine"},
    {"rifampicin", "rifampin"},
    {"ciclosporin", "cyclosporine", "cyclosporin"},
    {"pethidine", "meperidine"},
    {"amoxicillin", "amoxycillin"},
    {"glyceryl trinitrate", "nitroglycerin", "gtn"},
    {"metamizole", "dipyrone"},
]


def _expand_entities(entities: list[str] | None, use_synonyms: bool) -> list[str]:
    """Lowercase entities, optionally adding synonym-group members. Deduped."""
    out: list[str] = []
    for e in entities or []:
        el = (e or "").strip().lower()
        if not el:
            continue
        out.append(el)
        if use_synonyms:
            for grp in _SYNONYM_GROUPS:
                if any(m in el or el in m for m in grp):
                    out.extend(grp)
    seen: set[str] = set()
    res: list[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res

_STUDY_TYPE_SCORES: dict[str, float] = {
    "guideline": 10.0,
    "practice guideline": 9.0,
    "meta-analysis": 8.0,
    "systematic review": 8.0,
    "randomized controlled trial": 7.0,
    "rct": 7.0,
    "clinical trial": 6.0,
    "cohort study": 5.0,
    "cohort": 5.0,
    "cross-sectional": 4.0,
    "case-control": 4.0,
    "observational study": 3.0,
    "observational": 3.0,
    "review": 2.0,
    "case series": 2.0,
    "case report": 1.0,
    "letter": 0.0,
    "editorial": 0.0,
    "comment": 0.0,
}

_ANIMAL_RE = re.compile(
    r"\b(?:mouse|mice|rat\b|rats\b|murine|animal model|in vivo model|rodent|rabbit|canine|porcine)\b",
    re.IGNORECASE,
)
_PEDIATRIC_RE = re.compile(
    r"\b(?:pediatric|paediatric|children|infant|neonatal|adolescent)\b",
    re.IGNORECASE,
)


@dataclass
class ScoredArticle:
    article: dict[str, Any]
    score: float
    breakdown: dict[str, float]


def _score_study_type(article: dict[str, Any]) -> float:
    """Score based on publication type list and title/abstract text signals."""
    pub_types: list = article.get("pub_types") or article.get("publication_types") or []
    title: str = (article.get("title") or "").lower()
    abstract_head: str = (article.get("abstract") or "")[:300].lower()
    combined = " ".join(str(pt).lower() for pt in pub_types) + " " + title + " " + abstract_head
    best = 0.0
    for study_type, score in _STUDY_TYPE_SCORES.items():
        if study_type in combined:
            best = max(best, score)
    return best


def _score_relevance(article: dict[str, Any], entities: list[str], use_synonyms: bool = False) -> float:
    """Score entity presence in title (+3) and abstract head (+2), capped at 6.
    With use_synonyms, the entity's synonym-group members also count (paracetamol⇄acetaminophen)."""
    ents = _expand_entities(entities, use_synonyms)
    if not ents:
        return 0.0
    title = (article.get("title") or "").lower()
    abstract = (article.get("abstract") or "")[:500].lower()
    score = 0.0
    for el in ents:
        if el in title:
            score += 3.0
        elif el in abstract:
            score += 2.0
    return min(score, 6.0)


def _score_recency(article: dict[str, Any]) -> float:
    """Tiered recency score — foundational landmark evidence is still valuable.

    ≤5 years:   2.0  (most recent)
    6–15 years: 1.0  (current — covers 2010–present for 2025)
    16–25 years: 0.5  (foundational — landmark trials, e.g. HOPE 2000, ALLHAT 2002)
    >25 years:  0.0  (likely superseded)
    """
    try:
        year = int(str(article.get("year") or article.get("pub_date") or "0")[:4])
        if year < 1900:
            return 0.0
        age = _CURRENT_YEAR - year
        if age <= 5:
            return 2.0
        if age <= 15:
            return 1.0
        if age <= 25:
            return 0.5
    except (ValueError, TypeError):
        pass
    return 0.0


def _score_fulltext(article: dict[str, Any]) -> float:
    """Return 1.0 if PMCID (open full text) is available."""
    return 1.0 if (article.get("pmcid") or article.get("pmc_id")) else 0.0


def _score_citations(article: dict[str, Any]) -> float:
    """Return 1.0 if citation count >= 100."""
    try:
        if int(article.get("citation_count") or article.get("citations") or 0) >= 100:
            return 1.0
    except (ValueError, TypeError):
        pass
    return 0.0


def _compute_penalty(article: dict[str, Any], query_text: str) -> float:
    """Return negative penalty for animal-only or off-population studies."""
    title = (article.get("title") or "").lower()
    abstract = (article.get("abstract") or "")[:400].lower()
    combined = title + " " + abstract
    penalty = 0.0
    if _ANIMAL_RE.search(combined):
        penalty -= 3.0
    if _PEDIATRIC_RE.search(combined) and not _PEDIATRIC_RE.search(query_text.lower()):
        penalty -= 2.0
    return penalty


def score_article(
    article: dict[str, Any],
    entities: list[str],
    query_text: str,
    use_synonyms: bool = False,
) -> ScoredArticle:
    """Compute multi-factor evidence score for one article dict."""
    study = _score_study_type(article)
    relevance = _score_relevance(article, entities, use_synonyms=use_synonyms)
    recency = _score_recency(article)
    fulltext = _score_fulltext(article)
    citations = _score_citations(article)
    penalty = _compute_penalty(article, query_text)
    total = max(0.0, study + relevance + recency + fulltext + citations + penalty)
    return ScoredArticle(
        article=article,
        score=total,
        breakdown={
            "study_type": study,
            "relevance": relevance,
            "recency": recency,
            "fulltext": fulltext,
            "citations": citations,
            "penalty": penalty,
        },
    )


def rank_article_list(
    articles: list[dict[str, Any]],
    entities: list[str],
    query_text: str = "",
    *,
    use_synonyms: bool = False,
    apply_floor: bool = False,
    min_keep: int = 3,
) -> list[dict[str, Any]]:
    """Score and sort articles descending by evidence quality and relevance.

    Attaches `_rank_score` and `_rank_breakdown` to each article dict for observability.
    Default behaviour keeps every article (score-0 at the bottom).

    Relevance floor (apply_floor): DROP articles whose entity-relevance is 0 (the entity, and its
    synonyms when use_synonyms, appear nowhere) — so an off-topic article can't ride in on study-type
    or recency alone. Recall safeguard: always keep at least `min_keep` highest-scored articles, so a
    niche query with few on-topic hits isn't emptied. Input must be list[dict]; non-dicts pass through.
    """
    if not articles:
        return []

    dicts = [a for a in articles if isinstance(a, dict)]
    non_dicts = [a for a in articles if not isinstance(a, dict)]

    scored = [score_article(a, entities, query_text, use_synonyms=use_synonyms) for a in dicts]
    scored.sort(key=lambda x: x.score, reverse=True)

    result: list[dict[str, Any]] = []
    for sa in scored:
        enriched = dict(sa.article)
        enriched["_rank_score"] = sa.score
        enriched["_rank_breakdown"] = sa.breakdown
        result.append(enriched)

    if apply_floor and entities:
        relevant = [a for a in result if (a["_rank_breakdown"].get("relevance") or 0) > 0]
        irrelevant = [a for a in result if (a["_rank_breakdown"].get("relevance") or 0) == 0]
        if len(relevant) >= min_keep:
            result = relevant                      # enough on-topic → drop all entity-absent articles
        else:
            result = relevant + irrelevant[:max(0, min_keep - len(relevant))]  # keep some for recall

    return result + non_dicts
