"""Specialist-grade answer judge — deterministic rubric over a generated answer.

Imported by backend/tests/test_answer_judge.py; also runnable as a CLI.

NO BYOK spend. The answers are produced by a Claude Code model acting as the generator
(the standing preference: offline deterministic A/Bs + a Claude Code agent as generator/judge,
never the user's BYOK tokens). This file is the JUDGE, and it is mechanical on purpose: the
generation is the variable under test, so the scoring must not also be a matter of opinion.

What "reads like a decades-deep specialist" decomposes into, mechanically:

  R1 EVIDENCE WEIGHTING   names evidence strength in prose where it matters
  R2 LOE CORRECTNESS      loe derived from the cited source's tier (A/B->I, C->II, D->III)
  R3 NO REGISTRATION-AS-EVIDENCE  a Tier R protocol is never cited for efficacy
  R4 CALIBRATED HEDGING   when only low-tier evidence exists, the limit is stated outright
  R5 GROUNDING DENSITY    every clinical claim carries a resolvable source
  R6 NO FILLER            no sycophancy / hedging filler ("great question", "it is worth noting")
  R7 STRUCTURE            the sections a specialist would actually write for this query type

Usage: judge(answer_dict, tier_by_token) -> per-rule scores + failures.
Run standalone for the built-in OFF/ON comparison fixtures:
  docker exec -e PYTHONPATH=/app -w /app iatronix-dev-backend python3 judge_answer_quality.py
"""
import json
import re
import sys
from pathlib import Path

# Tier -> the LOE a specialist would assign (see prompt_engine._EVIDENCE_TIER_RULE)
_TIER_TO_LOE = {"A": "I", "B": "I", "C": "II", "D": "III", "T": "II", "R": "III"}
_LOW_TIERS = {"D", "R"}

# Phrases that mark evidence strength in prose — what a specialist actually writes.
_WEIGHT_MARKERS = re.compile(
    r"\b(guideline[- ]level|guideline[- ]based|meta[- ]analys|systematic review|randomi[sz]ed|"
    r"RCT|observational|case (report|series)|registration|not yet reported|low[- ]quality|"
    r"high[- ]quality|limited evidence|insufficient evidence|expert opinion|"
    r"tier [ABCDRT]|level [I]{1,3}\b)", re.I)

# Widened 2026-07-28: a blind multi-query run produced an ON answer that stated the limitation
# about as plainly as possible ("usefulness is unproven here", "no confident recommendation ...
# is justified", "no Tier A, B, or C evidence") and R4 still scored 0 — the marker list simply
# did not contain those phrasings. Like the R3 negation bug, the defect was in the SCORER, not
# the answer. Any rubric rule that fires on a fixed vocabulary needs its vocabulary tested
# against text an independent generator actually writes.
_LIMIT_MARKERS = re.compile(
    r"\b(limited|insufficient|sparse|weak|low[- ]quality|low[- ]tier|no (randomi|controlled|direct)|"
    r"not established|cannot be determined|uncertain|caution|unproven|not proven|"
    r"no (confident|firm|graded) recommendation|cannot (be )?(support|justif|conclude|recommend)|"
    r"not justified|hypothesis[- ]generating|no tier [abc]|absence of evidence|"
    r"no (high|higher)[- ]tier)\b", re.I)

_EFFICACY = re.compile(r"\b(reduces?|improves?|lowers?|prevents?|is effective|efficacious|"
                       r"superior|benefit)\b", re.I)
# A claim that EXPLICITLY refuses to treat a registration as evidence is the correct specialist
# behaviour, not a violation — "...is NOT evidence that X is effective" must not trip R3. Without
# this, the rubric penalised exactly the sentence it should reward (caught 2026-07-28 when an
# independent generator wrote the ideal answer and scored 0 on R3).
_NEGATED_EFFICACY = re.compile(
    r"\b(not|cannot|can not|no|never|without)\b[^.]{0,80}?\b"
    r"(evidence|establish|support|conclude|claim|prove|demonstrat)", re.I)


def _asserts_efficacy(text: str) -> bool:
    """True only when the claim ASSERTS efficacy, not when it disclaims it."""
    if not _EFFICACY.search(text or ""):
        return False
    for sent in re.split(r"(?<=[.;])\s+", text or ""):
        if _EFFICACY.search(sent) and not _NEGATED_EFFICACY.search(sent):
            return True
    return False

_FILLER = re.compile(
    r"\b(great question|excellent question|as an ai|i hope this helps|it('s| is) worth noting|"
    r"generally believed|some may argue|arguably|in my opinion|it should be noted that)\b", re.I)


def _items(answer: dict) -> list[dict]:
    out = []
    for s in answer.get("sections", []) or []:
        out.extend(i for i in (s.get("content_items") or []) if isinstance(i, dict))
    return out


def _all_prose(answer: dict) -> str:
    b = answer.get("bluf") or {}
    parts = [b.get("headline") or "", b.get("body") or ""]
    parts += list(b.get("key_points") or []) + list(b.get("caveats") or [])
    parts += [i.get("text") or "" for i in _items(answer)]
    parts += [s.get("title") or "" for s in answer.get("sections", []) or []]
    return "\n".join(parts)


def judge(answer: dict, tier_by_token: dict[str, str], expected_sections: int = 3) -> dict:
    items = _items(answer)
    prose = _all_prose(answer)
    fails: list[str] = []
    scores: dict[str, float] = {}

    tiers_present = set(tier_by_token.values())
    only_low = tiers_present and tiers_present.issubset(_LOW_TIERS)

    # R1 — does the prose actually signal evidence strength?
    n_marks = len(_WEIGHT_MARKERS.findall(prose))
    scores["R1_evidence_weighting"] = 1.0 if n_marks >= 2 else (0.5 if n_marks == 1 else 0.0)
    if n_marks == 0:
        fails.append("R1: prose never signals evidence strength — reads as a flat summary")

    # R2 — loe must follow the cited source's tier
    checked = wrong = 0
    for it in items:
        tok = (it.get("ref_token") or "").upper()
        tier = tier_by_token.get(tok)
        loe = (it.get("loe") or "").strip().upper().rstrip(".")
        if tier and loe:
            checked += 1
            if loe != _TIER_TO_LOE.get(tier):
                wrong += 1
                fails.append(f"R2: {tok} is Tier {tier} but loe={loe} "
                             f"(expected {_TIER_TO_LOE.get(tier)})")
    scores["R2_loe_correct"] = 1.0 if checked and not wrong else (0.0 if checked else None)

    # R3 — a registration must never back an efficacy claim
    bad_reg = [it for it in items
               if tier_by_token.get((it.get("ref_token") or "").upper()) == "R"
               and _asserts_efficacy(it.get("text") or "")]
    scores["R3_no_registration_as_evidence"] = 0.0 if bad_reg else 1.0
    for it in bad_reg:
        fails.append(f"R3: efficacy claim cites a trial REGISTRATION: {(it.get('text') or '')[:70]}")

    # R4 — if only low-tier evidence exists, say so
    if only_low:
        stated = bool(_LIMIT_MARKERS.search(prose))
        scores["R4_calibrated_hedging"] = 1.0 if stated else 0.0
        if not stated:
            fails.append("R4: only low-tier evidence available but no limitation stated")
    else:
        scores["R4_calibrated_hedging"] = None

    # R5 — grounding density
    if items:
        grounded = sum(1 for it in items
                       if (it.get("source") or "").strip()
                       and it.get("source") != "Expert opinion")
        dens = grounded / len(items)
        scores["R5_grounding_density"] = round(dens, 2)
        if dens < 0.8:
            fails.append(f"R5: only {grounded}/{len(items)} claims carry a real source")
    else:
        scores["R5_grounding_density"] = 0.0
        fails.append("R5: no content items at all")

    # R6 — no filler
    hits = _FILLER.findall(prose)
    scores["R6_no_filler"] = 1.0 if not hits else 0.0
    if hits:
        fails.append(f"R6: filler/sycophancy present: {hits[:3]}")

    # R7 — structure
    n_sec = len(answer.get("sections") or [])
    scores["R7_structure"] = 1.0 if n_sec >= expected_sections else round(n_sec / expected_sections, 2)
    if n_sec < expected_sections:
        fails.append(f"R7: {n_sec} sections, expected >= {expected_sections}")

    graded = [v for v in scores.values() if v is not None]
    return {"scores": scores, "overall": round(sum(graded) / len(graded), 3),
            "fails": fails}


def _report(name: str, res: dict) -> None:
    print(f"\n=== {name} — overall {res['overall']:.2f} ===")
    for k, v in res["scores"].items():
        print(f"   {k:<34}{'n/a' if v is None else v}")
    for f in res["fails"]:
        print(f"   FAIL {f}")


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    fixtures = Path("/app/judge_fixtures.json")
    if not fixtures.exists():
        print("no /app/judge_fixtures.json — generate answers first")
        sys.exit(2)
    data = json.loads(fixtures.read_text())
    tiers = data["tier_by_token"]
    out = {}
    for arm in ("off", "on"):
        out[arm] = judge(data[arm], tiers, expected_sections=data.get("expected_sections", 3))
        _report(f"FLAG {arm.upper()}", out[arm])
    print(f"\nOVERALL  OFF {out['off']['overall']:.2f}  ->  ON {out['on']['overall']:.2f}  "
          f"(delta {out['on']['overall'] - out['off']['overall']:+.2f})")
    Path("/app/judge_result.json").write_text(json.dumps(out, indent=2))
    print("saved -> /app/judge_result.json")
