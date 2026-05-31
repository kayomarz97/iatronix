"""Answer-quality checks (Phase 5d) — detect sycophancy + uncited claims.

Pure, LLM-free functions usable both as an eval (tests fail on violations) and as
a lightweight runtime guard. Enforces the evidence-only / no-sycophancy contract.
"""

from __future__ import annotations

import re
from typing import Any

# Flattery / meta-commentary / model-voice opinion + hedging filler.
_BAD_PHRASE_PATTERNS = [
    r"\bgreat question\b",
    r"\bexcellent question\b",
    r"\bgood question\b",
    r"\bas an expert\b",
    r"\bit'?s worth noting\b",
    r"\bi hope this helps\b",
    r"\bfeel free to\b",
    r"\bas you (?:may|might) know\b",
    r"\bin my opinion\b",
    r"\bi believe\b",
    r"\bi'?d recommend\b",
    r"\bit is generally believed\b",
    r"\bsome (?:may|might) argue\b",
    r"\barguably\b",
    r"\bgenerally speaking\b",
]
_BAD_PHRASE_RE = re.compile("|".join(_BAD_PHRASE_PATTERNS), re.IGNORECASE)

# Sources that count as "cited" — including the permitted low-confidence fallback.
_CITED_SOURCELESS_SENTINELS = {"__unresolved_token__"}


def find_sycophantic_phrases(text: str) -> list[str]:
    """Return every flattery/hedging match in ``text`` (empty list = clean)."""
    return [m.group(0) for m in _BAD_PHRASE_RE.finditer(text or "")]


def is_sycophantic(text: str) -> bool:
    return bool(find_sycophantic_phrases(text))


def _iter_content_items(response: dict[str, Any]):
    for sec in (response or {}).get("sections", []) or []:
        if not isinstance(sec, dict):
            continue
        for item in sec.get("content_items", []) or []:
            if isinstance(item, dict):
                yield item


def find_uncited_claims(response: dict[str, Any]) -> list[str]:
    """Return claim texts whose ``source`` is empty/missing (uncited).

    "Expert opinion" counts as cited (the permitted demoted fallback). Only a
    genuinely empty/sentinel source is a violation.
    """
    out: list[str] = []
    for item in _iter_content_items(response):
        src = str(item.get("source") or "").strip().lower()
        if not src or src in _CITED_SOURCELESS_SENTINELS:
            val = item.get("value") or item.get("text") or ""
            out.append(str(val)[:120])
    return out


def check_answer(response: dict[str, Any]) -> dict[str, list[str]]:
    """Combined eval. Returns {"sycophancy": [...], "uncited": [...]}; both empty = pass.

    Scans BLUF + all section content for sycophantic phrasing, and flags any
    content item lacking a source.
    """
    texts: list[str] = []
    bluf = (response or {}).get("bluf") or {}
    if isinstance(bluf, dict):
        texts.append(str(bluf.get("headline", "")))
        texts.append(str(bluf.get("body", "")))
    for item in _iter_content_items(response):
        texts.append(str(item.get("value") or item.get("text") or ""))

    sycophancy: list[str] = []
    for t in texts:
        sycophancy.extend(find_sycophantic_phrases(t))

    return {"sycophancy": sycophancy, "uncited": find_uncited_claims(response)}
