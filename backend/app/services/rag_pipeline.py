import asyncio
import json
import logging
import re
import time

import pybreaker
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import settings
from app.db.session import async_session
from app.models.query_log import QueryLog
from app.schemas.query import (
    ComparativeResponse,
    DegradedResponse,
    DiseaseResponse,
    DrugResponse,
    EvidenceResponse,
    GeneralResponse,
    ProcedureResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.cache import cache_get, cache_get_any_version, cache_set
from app.services.circuit_breaker import get_breaker, is_provider_available
from app.services.citation_validator import validate_citations
from app.services.data_fetcher import FetchedData, fetch_data_for_query
from app.services.scraping_response import _build_scraping_response
from app.services.semantic_cache import (
    is_stale,
    semantic_cache_get,
    semantic_cache_revalidate,
    semantic_cache_set,
)
from app.services.drug_linker import process_text_nodes
from app.services.json_repair import parse_llm_json
from app.services.llm_factory import create_llm, get_provider
from app.services.prompt_engine import build_prompt
from app.services.query_classifier import classify_query, detect_intent
from app.services.safety_checker import check_safety
from app.services.url_builder import enrich_references
from app.services.source_router import route_query
from app.services.vector_search import search as vector_search

# PMID/DOI hyperlinking patterns


logger = logging.getLogger(__name__)


def _summarize_fetched(fetched_data: "FetchedData") -> str:
    """Summarize fetched API data for DSPy input — include all raw fields."""
    parts = []
    if fetched_data.drug_data:
        d = fetched_data.drug_data
        raw_fields = [
            ("drug", d.generic_name or ""),
            ("indications", d.indications_raw or ""),
            ("dosing", d.dosing_raw or ""),
            ("contraindications", d.contraindications_raw or ""),
            ("warnings", d.warnings_raw or ""),
            ("adverse_reactions", d.adverse_reactions_raw or ""),
            ("special_populations", d.special_populations_raw or ""),
            ("mechanism", d.mechanism_raw or ""),
            ("pharmacokinetics", d.pharmacokinetics_raw or ""),
            ("interactions", d.drug_interactions_raw or ""),
        ]
        for label, val in raw_fields:
            if val:
                parts.append(f"[{label}]: {val[:600]}")
        for ab in (d.guideline_abstracts or [])[:3]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:300]
            if title or abstract:
                parts.append(f"[guideline]: {title} — {abstract}")
        for ab in (d.systematic_review_abstracts or [])[:2]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:300]
            if title or abstract:
                parts.append(f"[systematic_review]: {title} — {abstract}")
    if fetched_data.disease_data:
        dd = fetched_data.disease_data
        if dd.medlineplus_summary:
            parts.append(f"[medlineplus]: {dd.medlineplus_summary[:500]}")
        for ab in (dd.guideline_abstracts or [])[:4]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:300]
            if title or abstract:
                parts.append(f"[guideline]: {title} — {abstract}")
        for ab in (dd.systematic_review_abstracts or [])[:2]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:300]
            if title or abstract:
                parts.append(f"[systematic_review]: {title} — {abstract}")
    if fetched_data.evidence_data:
        ed = fetched_data.evidence_data
        for ab in (ed.systematic_review_abstracts or [])[:3]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:300]
            if title or abstract:
                parts.append(f"[systematic_review]: {title} — {abstract}")
        for ab in (ed.clinical_trial_abstracts or [])[:3]:
            title = ab.get("title", "")
            abstract = ab.get("abstract", "")[:300]
            if title or abstract:
                parts.append(f"[clinical_trial]: {title} — {abstract}")
    return "\n".join(parts)[:6000] if parts else ""


def _summarize_vectors(vector_results: list) -> str:
    """Summarize vector search results for DSPy input."""
    if not vector_results:
        return ""
    return "\n".join(str(r)[:300] for r in vector_results[:5])


def _describe_data(fetched_data: "FetchedData") -> str:
    """Describe what data sources were fetched."""
    sources = []
    if fetched_data.drug_data:
        sources.append(fetched_data.drug_data.data_source or "FDA label")
    if fetched_data.disease_data and fetched_data.disease_data.guideline_abstracts:
        sources.append("PubMed guidelines")
    return ", ".join(sources) if sources else "none"


DISCLAIMER = (
    "This information is generated by AI for educational and clinical decision support purposes only. "
    "It does not replace professional medical judgment. Always verify with current clinical guidelines "
    "and consult appropriate specialists. Patient-specific factors must be considered."
)

RESPONSE_MODELS = {
    "drug": DrugResponse,
    "disease": DiseaseResponse,
    "comparative": ComparativeResponse,
    "procedure": ProcedureResponse,
    "evidence": EvidenceResponse,
    "general": GeneralResponse,
}

# Regex to extract condition from drug queries like "digoxin in AF", "metformin for diabetes"
_CONDITION_RE = re.compile(
    r"\b(?:in|for)\s+([A-Za-z][A-Za-z0-9\s\-]{2,40}?)(?:\s*[,?.]|$)",
    re.IGNORECASE,
)


def _is_critically_sparse(data: dict, query_type: str) -> tuple[bool, list[str]]:
    """Detect if an LLM response is critically sparse and needs a retry.

    Returns (is_sparse, list_of_reasons).
    """
    reasons: list[str] = []
    if query_type == "disease":
        if len(data.get("clinical_features", [])) < 4:
            reasons.append(
                f"clinical_features only {len(data.get('clinical_features', []))} entries (need 8+)"
            )
        if not data.get("treatment", {}).get("first_line"):
            reasons.append("treatment.first_line empty")
        if len(data.get("diagnostic_criteria", [])) < 3:
            reasons.append(
                f"diagnostic_criteria only {len(data.get('diagnostic_criteria', []))} entries (need 6+)"
            )
        if not data.get("etiology"):
            reasons.append("etiology empty")
        if not data.get("prognosis"):
            reasons.append("prognosis missing")
        return len(reasons) >= 2, reasons
    elif query_type == "drug":
        if not data.get("dosing") and not data.get("indications"):
            reasons.append("dosing and indications both empty")
            return True, reasons
        if (
            len(data.get("side_effects", [])) < 3
            and len(data.get("interactions", [])) < 3
        ):
            reasons.append(
                f"side_effects={len(data.get('side_effects', []))} and interactions={len(data.get('interactions', []))} both < 3"
            )
            return True, reasons
    elif query_type == "comparative":
        n_dims = len(data.get("detailed_comparison", []))
        if n_dims < 6:
            reasons.append(f"detailed_comparison only {n_dims} dimensions (need 8+)")
            return True, reasons
    elif query_type == "evidence":
        n_supporting = len(data.get("supporting_studies", []))
        if n_supporting < 2:
            reasons.append(f"supporting_studies only {n_supporting} (need 3+)")
            return True, reasons
        summary = data.get("summary", "")
        if not summary or len(summary) < 100:
            reasons.append("summary too short (need 4-6 sentences)")
            return True, reasons
    elif query_type == "procedure":
        n_steps = len(data.get("technique_steps", []))
        if n_steps < 3:
            reasons.append(f"technique_steps only {n_steps} (need 5+)")
            return True, reasons
    return False, []


# Model tier ranking — higher number = more capable
# Used to ensure user's model choice is never downgraded by routing
def _model_tier(model_id: str) -> int:
    """Return a tier number for a model — higher = more capable."""
    m = model_id.lower()
    if "opus" in m:
        return 3
    if "sonnet" in m:
        return 2
    if "haiku" in m:
        return 1
    # Unknown models (e.g. OpenRouter) — treat as mid-tier
    return 2


# Async log queue
_log_queue: asyncio.Queue | None = None
_log_task: asyncio.Task | None = None


async def init_log_queue():
    """Initialize the async logging queue and consumer."""
    global _log_queue, _log_task
    _log_queue = asyncio.Queue(maxsize=settings.log_queue_max_size)
    _log_task = asyncio.create_task(_log_consumer())


async def shutdown_log_queue():
    """Shutdown the async logging queue."""
    global _log_task
    if _log_task:
        _log_task.cancel()
        try:
            await _log_task
        except asyncio.CancelledError:
            pass


async def _log_consumer():
    """Drain the log queue and write to DB."""
    while True:
        try:
            entry = await _log_queue.get()
            await _write_log_entry(entry)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.error("Log consumer error", exc_info=True)


async def _write_log_entry(entry: dict):
    """Write a log entry to DB with retry and file fallback."""
    for attempt in range(settings.log_db_retry_max + 1):
        try:
            async with async_session() as session:
                # Truncate oversized response
                response_json = entry.get("response_json", {})
                response_str = json.dumps(response_json)
                truncated = False
                if len(response_str.encode()) > settings.max_response_jsonb_bytes:
                    response_str = response_str[: settings.truncated_response_bytes]
                    response_json = json.loads(response_str + "}")  # best effort
                    truncated = True

                log = QueryLog(
                    query=entry["query"],
                    query_type=entry["query_type"],
                    model_used=entry["model_used"],
                    response_json=response_json,
                    latency_ms=entry["latency_ms"],
                    cached=entry.get("cached", False),
                    truncated=truncated,
                    user_key_id=entry.get("user_key_id"),
                )
                session.add(log)
                await session.commit()
                return
        except Exception:
            if attempt < settings.log_db_retry_max:
                await asyncio.sleep(settings.log_db_retry_backoff)
            else:
                # File fallback
                logger.error(
                    "DB log write failed after retries, writing to file", exc_info=True
                )
                try:
                    import aiofiles

                    async with aiofiles.open(
                        "/app/logs/query_log_fallback.jsonl", "a"
                    ) as f:
                        await f.write(json.dumps(entry, default=str) + "\n")
                except Exception:
                    # Last resort: structured log
                    logger.error(f"FALLBACK_LOG: {json.dumps(entry, default=str)}")


async def _enqueue_log(entry: dict):
    """Add a log entry to the async queue."""
    if _log_queue is None:
        return
    try:
        _log_queue.put_nowait(entry)
    except asyncio.QueueFull:
        logger.warning("Log queue full, dropping oldest entry")
        try:
            _log_queue.get_nowait()
            _log_queue.put_nowait(entry)
        except Exception:
            pass


async def _call_llm(
    model_id: str,
    prompt: str,
    max_tokens: int | None = None,
    user_key: str | None = None,
    user_provider: str | None = None,
) -> str | None:
    """Call LLM with circuit breaker protection (BYOK — user key required)."""
    provider = user_provider or get_provider(model_id)
    breaker = get_breaker(provider)

    # Raises HTTP 402 if no key — let it propagate up to process_query
    llm = create_llm(
        model_id, max_tokens=max_tokens, user_key=user_key, user_provider=user_provider
    )

    try:

        @breaker
        async def _invoke():
            response = await llm.ainvoke(prompt)
            return response.content

        return await _invoke()
    except pybreaker.CircuitBreakerError:
        logger.warning(f"Circuit breaker open for {provider}")
        return None
    except HTTPException:
        raise
    except Exception:
        logger.error(f"LLM call failed for {model_id}", exc_info=True)
        return None


_CLAIM_FIELDS = {"loe", "cor", "source", "confidence", "value"}
_VALID_LOE = {"I", "II-1", "II-2", "II-3", "III"}
_VALID_COR = {"I", "IIa", "IIb", "III-no-benefit", "III-harm"}


def _coerce_evidenced_claims(obj: object) -> None:
    """Recursively fill missing/invalid required EvidencedClaim fields with safe defaults.

    Safety rule: claims with no source get LOE III + COR IIb + low confidence
    to prevent unsourced claims from appearing authoritative.
    """
    if isinstance(obj, dict):
        if "value" in obj or (_CLAIM_FIELDS & obj.keys()):
            has_source = bool(
                obj.get("source")
                and obj["source"] not in ("Clinical guidelines", "Expert opinion")
            )

            loe = obj.get("loe") or ""
            if isinstance(loe, str):
                loe = loe.strip()
            if not loe or loe not in _VALID_LOE:
                obj["loe"] = "III"

            cor = obj.get("cor") or ""
            if isinstance(cor, str):
                cor = cor.strip()
            if not cor or cor not in _VALID_COR:
                # Unsourced claims must NOT get Class I (strongest recommendation)
                obj["cor"] = "IIb" if not has_source else "IIa"

            # LOE↔COR consistency enforcement (patient safety)
            final_loe = obj["loe"]
            final_cor = obj.get("cor", "IIb")
            if final_loe == "III" and final_cor == "I":
                # LOE III (expert opinion) must never claim COR I (strongest)
                obj["cor"] = "IIb"
            elif final_loe == "I" and final_cor == "IIb":
                # LOE I (RCT) shouldn't be downgraded to IIb
                obj["cor"] = "IIa"

            if not obj.get("source"):
                obj["source"] = "Expert opinion"

            # Normalize confidence to lowercase (LLM may return "MODERATE")
            conf = obj.get("confidence") or ""
            if isinstance(conf, str):
                conf = conf.strip().lower()
            if conf not in ("high", "moderate", "low"):
                obj["confidence"] = "low" if not has_source else "moderate"
            else:
                obj["confidence"] = conf
        for v in obj.values():
            _coerce_evidenced_claims(v)
    elif isinstance(obj, list):
        for item in obj:
            _coerce_evidenced_claims(item)


def _validate_response(data: dict, query_type: str) -> tuple[dict | None, list[str]]:
    """Validate response structurally (Pydantic) and semantically."""
    warnings = []
    model_cls = RESPONSE_MODELS.get(query_type)
    if not model_cls:
        return data, ["Unknown query type"]

    # Fill in missing required EvidencedClaim fields before validation
    _coerce_evidenced_claims(data)

    try:
        validated = model_cls.model_validate(data)
        data = validated.model_dump()
    except ValidationError as e:
        logger.warning(f"Pydantic validation failed: {e}")
        return None, [f"Structural validation failed: {str(e)[:200]}"]

    # Semantic validation
    if query_type == "drug":
        if not data.get("drug_name"):
            warnings.append("Missing drug_name in response")
        if not data.get("dosing"):
            warnings.append("No dosing information provided")
        # Check duplicate interactions
        interactions = data.get("interactions", [])
        seen_drugs = set()
        for ix in interactions:
            drug = ix.get("drug", "").lower()
            if drug in seen_drugs:
                warnings.append(f"Duplicate interaction entry: {drug}")
            seen_drugs.add(drug)

    elif query_type == "disease":
        if not data.get("disease_name"):
            warnings.append("Missing disease_name in response")
        treatment = data.get("treatment", {})
        if not treatment.get("first_line"):
            warnings.append("No first-line treatment provided")
        if not data.get("diagnostic_criteria"):
            warnings.append("No diagnostic criteria provided")
        if (
            not data.get("clinical_features")
            or len(data.get("clinical_features", [])) < 3
        ):
            warnings.append("Insufficient clinical features — expected 6+ entries")
        if not data.get("etiology"):
            warnings.append("No etiology provided")
        if not data.get("prognosis"):
            warnings.append("No prognosis provided")
        if not data.get("pathophysiology"):
            warnings.append("No pathophysiology provided")
        if not treatment.get("non_pharmacological"):
            warnings.append("No non-pharmacological treatment provided")

    elif query_type == "comparative":
        compared = data.get("entities_compared", [])
        if len(compared) < 2:
            warnings.append("Fewer than 2 entities compared")
        if not data.get("detailed_comparison"):
            warnings.append("No detailed comparison provided")

    return data, warnings


async def _log_search_history(
    user_id: int, query_text: str, query_type: str, result: dict
):
    """Fire-and-forget: persist a search history entry for the user."""
    try:
        from app.db.session import async_session as session_factory
        from app.models.search_history import SearchHistory
        from sqlalchemy import select, func

        async with session_factory() as session:
            # Enforce max 100 entries per user
            count_result = await session.execute(
                select(func.count())
                .select_from(SearchHistory)
                .where(SearchHistory.user_id == user_id)
            )
            count = count_result.scalar() or 0
            if count >= 100:
                oldest = await session.execute(
                    select(SearchHistory)
                    .where(SearchHistory.user_id == user_id)
                    .order_by(SearchHistory.created_at.asc())
                    .limit(1)
                )
                old = oldest.scalar_one_or_none()
                if old:
                    await session.delete(old)
            summary = str(result)[:300] if result else ""
            session.add(
                SearchHistory(
                    user_id=user_id,
                    query_text=query_text,
                    query_type=query_type,
                    response_summary=summary,
                )
            )
            await session.commit()
    except Exception as e:
        logger.debug(f"Search history logging failed: {e}")


async def process_query(
    request: QueryRequest,
    redis_client=None,
    user_key_id: str | None = None,
    user=None,
) -> QueryResponse:
    """Main RAG pipeline orchestrator."""
    start_time = time.time()

    # Resolve user's BYOK key (only user-supplied key is used — no server .env fallback)
    user_llm_key: str | None = None
    user_llm_provider: str | None = None
    if user and user.encrypted_llm_key:
        from app.services.byok import decrypt_key

        user_llm_key = decrypt_key(user.encrypted_llm_key)
        user_llm_provider = user.llm_provider
        if user_llm_key is None:
            # Decryption failed (e.g. ENCRYPTION_KEY changed after restart)
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(
                query_type="general",
                model_used=request.model_id,
                response=DegradedResponse(
                    message="Your API key could not be retrieved — please re-enter it in Settings.",
                    suggestion="Go to Settings → LLM API Key and save your key again. This happens when the server restarts without a stable ENCRYPTION_KEY.",
                ),
                disclaimer=DISCLAIMER,
                latency_ms=latency_ms,
            )

    # Classify
    query_type, confidence = classify_query(request.query, request.query_type)
    query_intent = detect_intent(request.query)
    # Only override to general for highlights when query is already unstructured.
    # Keep drug/disease/comparative/procedure/evidence types so structured schemas are preserved.
    if query_intent == "highlights" and query_type not in (
        "drug",
        "disease",
        "comparative",
        "procedure",
        "evidence",
    ):
        query_type = "general"

    # Extract condition context for drug queries (e.g. "digoxin in AF" → condition = "AF")
    condition_context: str | None = None
    if query_type == "drug":
        m = _CONDITION_RE.search(request.query)
        condition_context = m.group(1).strip() if m else None

    # Track query frequency for self-improvement (fire-and-forget)
    if redis_client:
        try:
            normalized = request.query.strip().lower()
            await redis_client.zincrby(
                "iatronix:query_freq", 1, f"{query_type}:{normalized}"
            )
            await redis_client.zincrby("iatronix:type_freq", 1, query_type)
        except Exception:
            pass  # non-critical

    # Cache check
    cached_data = await cache_get(
        redis_client, request.query, query_type, request.model_id
    )
    if cached_data:
        latency_ms = int((time.time() - start_time) * 1000)
        cached_data["cached"] = True
        cached_data["latency_ms"] = latency_ms
        response = QueryResponse(**cached_data)
        await _enqueue_log(
            {
                "query": request.query,
                "query_type": query_type,
                "model_used": request.model_id,
                "response_json": cached_data,
                "latency_ms": latency_ms,
                "cached": True,
                "user_key_id": user_key_id,
            }
        )
        return response

    # Semantic cache check (pgvector cosine similarity — SWR)
    sem_response, sem_cache_id = await semantic_cache_get(
        request.query, query_type, request.model_id
    )
    if sem_response:
        latency_ms = int((time.time() - start_time) * 1000)
        sem_response["cached"] = True
        sem_response["latency_ms"] = latency_ms
        try:
            response = QueryResponse(**sem_response)
        except Exception:
            response = None

        if response:
            # SWR: if stale, trigger background revalidation but still return hit
            _sem_stale = is_stale(
                sem_response.get("_last_verified_at"),
                settings.semantic_cache_swr_ttl_seconds,
            )
            if _sem_stale and sem_cache_id:
                logger.debug(
                    "Semantic cache hit is stale — scheduling revalidation id=%d",
                    sem_cache_id,
                )
                # Background revalidation will be fired after returning the response below
                asyncio.create_task(
                    _revalidate_semantic_cache(
                        request,
                        query_type,
                        sem_cache_id,
                        redis_client,
                        user_key_id,
                        user_llm_key,
                        user_llm_provider,
                        user=user,
                    )
                )
            return response

    # Circuit breaker check
    provider = user_llm_provider or get_provider(request.model_id)
    if not is_provider_available(provider):
        # Try cached response (any version)
        any_cached = await cache_get_any_version(
            redis_client, request.query, query_type, request.model_id
        )
        if any_cached:
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(**any_cached, cached=True, latency_ms=latency_ms)

        # Degraded response — circuit is open, no fallback provider in BYOK mode
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            query_type=query_type,
            model_used=request.model_id,
            response=DegradedResponse(),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
        )

    # Route and fetch external data + vector search in parallel
    # source_mode: "ai" = full pipeline, "scraping" = API only (no vector), "pdfs" = vector only
    source_mode = getattr(request, "source_mode", "ai")
    use_api_fetch = settings.api_fetch_enabled and source_mode != "pdfs"
    use_vector = settings.vector_search_enabled and source_mode != "scraping"

    fetched_data: FetchedData | None = None
    vector_results = []
    routing = None

    tasks = {}
    if use_api_fetch:
        routing = route_query(request.query, query_type)
        if routing.fetch_enabled:
            tasks["api"] = asyncio.wait_for(
                fetch_data_for_query(
                    query_type,
                    routing.entities,
                    condition_context=condition_context,
                ),
                timeout=settings.api_fetch_timeout_seconds + 1.0,
            )

    if use_vector:
        tasks["vector"] = vector_search(request.query)

    if tasks:
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), results):
            if key == "api":
                if isinstance(result, asyncio.TimeoutError):
                    logger.warning("API fetch timed out — using generate mode")
                    fetched_data = FetchedData(
                        query_type=query_type, fallback_to_llm=True
                    )
                elif isinstance(result, Exception):
                    logger.warning("API fetch error: %s", result)
                else:
                    fetched_data = result
            elif key == "vector":
                if isinstance(result, Exception):
                    logger.warning("Vector search error: %s", result)
                else:
                    vector_results = result

    # Scraping-only mode: skip LLM and return raw API data directly
    if source_mode == "scraping":
        raw_resp = _build_scraping_response(request.query, query_type, fetched_data)
        if raw_resp is not None:
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(
                query_type=query_type,
                model_used="none",
                response=raw_resp,
                disclaimer=(
                    "Raw data from medical databases (OpenFDA, PubMed, RxNorm). "
                    "Not AI-formatted or verified. Use clinical judgment."
                ),
                latency_ms=latency_ms,
            )

    # Model and token budget selection
    # If user explicitly chose a model, respect it unconditionally.
    # Routing only applies when user is on the default (auto) model.
    effective_model = request.model_id
    max_tokens = settings.llm_max_tokens_generate
    if (
        settings.model_routing_enabled
        and not request.model_explicit  # user did NOT explicitly pick — allow routing
        and routing is not None  # only set when api fetch path was taken
        and fetched_data is not None
        and not fetched_data.fallback_to_llm
        and (user_llm_provider == "anthropic" or "/" not in request.model_id)
    ):
        effective_model = routing.preferred_model
        if query_type == "disease":
            max_tokens = settings.llm_max_tokens_format_disease
        elif query_type == "evidence":
            max_tokens = settings.llm_max_tokens_format_evidence
        elif query_type == "procedure":
            max_tokens = settings.llm_max_tokens_format_procedure
        elif query_type == "drug" and condition_context:
            max_tokens = settings.llm_max_tokens_format_drug_context
            # Drug-in-condition needs synthesis capability — upgrade to Sonnet
            if not request.model_explicit and (
                user_llm_provider == "anthropic" or "/" not in request.model_id
            ):
                effective_model = settings.model_sonnet
        else:
            max_tokens = settings.llm_max_tokens_format
    elif query_type == "disease":
        # Disease generate mode — force Sonnet when routing wasn't set (no entities extracted)
        max_tokens = settings.llm_max_tokens_format_disease
        if not request.model_explicit and (
            user_llm_provider == "anthropic" or "/" not in request.model_id
        ):
            effective_model = settings.model_sonnet
    elif query_type == "evidence":
        max_tokens = settings.llm_max_tokens_format_evidence
    elif query_type == "procedure":
        max_tokens = settings.llm_max_tokens_format_procedure
    elif query_type == "drug" and condition_context:
        max_tokens = settings.llm_max_tokens_format_drug_context
        # Drug-in-condition needs synthesis capability — upgrade to Sonnet
        if not request.model_explicit and (
            user_llm_provider == "anthropic" or "/" not in request.model_id
        ):
            effective_model = settings.model_sonnet

    # DSPy adaptive path
    if settings.dspy_enabled:
        try:
            import dspy as _dspy
            from app.services.dspy_lm import get_dspy_lm
            from app.services.dspy_modules import AdaptiveMedicalPipeline
            from app.schemas.query import AdaptiveSection, AdaptiveResponse

            _lm = get_dspy_lm(
                effective_model,
                user_llm_key or settings.anthropic_api_key,
                user_llm_provider or "anthropic",
            )
            with _dspy.context(lm=_lm):
                _pipeline = AdaptiveMedicalPipeline()
                _analysis, _dspy_resp = _pipeline(
                    query=request.query,
                    fetched_data=_summarize_fetched(fetched_data)
                    if fetched_data
                    else "",
                    vector_results=_summarize_vectors(vector_results),
                    available_data_types=_describe_data(fetched_data)
                    if fetched_data
                    else "none",
                )
            _resp_dict = json.loads(_dspy_resp.response_json)
            _sections = [AdaptiveSection(**s) for s in _resp_dict.get("sections", [])]
            _adaptive = AdaptiveResponse(
                query_type=_analysis.query_type,
                bluf=_dspy_resp.bluf,
                sections=_sections,
                references=_resp_dict.get("references", []),
                response_focus=_analysis.response_focus,
                depth=_analysis.depth,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            return QueryResponse(
                query_type="adaptive",
                model_used=effective_model,
                response=_adaptive,
                latency_ms=latency_ms,
                disclaimer=DISCLAIMER,
            )
        except Exception as _dspy_err:
            logger.warning(
                "DSPy path failed, falling back to standard pipeline: %s", _dspy_err
            )

    prompt_mode = (
        "format" if (fetched_data and not fetched_data.fallback_to_llm) else "generate"
    )
    fetch_latency_ms = fetched_data.total_fetch_time_ms if fetched_data else 0

    # Build prompt (format-mode if API data available, generate-mode otherwise)
    prompt = build_prompt(
        request.query,
        query_type,
        fetched_data,
        vector_results,
        intent=query_intent,
        condition_context=condition_context,
    )

    # LLM call with retry
    try:
        raw_response = await _call_llm(
            effective_model,
            prompt,
            max_tokens=max_tokens,
            user_key=user_llm_key,
            user_provider=user_llm_provider,
        )
    except HTTPException as e:
        if e.status_code == 402:
            # Graceful degradation: no API key — return raw scraped data with warning
            latency_ms = int((time.time() - start_time) * 1000)
            raw_sources = {}
            if fetched_data:
                if fetched_data.drug_data:
                    d = fetched_data.drug_data
                    raw_sources["drug"] = {
                        "name": d.generic_name,
                        "brand": d.brand_name,
                        "source": d.data_source,
                        "indications": d.indications_raw,
                        "dosing": d.dosing_raw,
                        "contraindications": d.contraindications_raw,
                        "adverse_reactions": d.adverse_reactions_raw,
                    }
                if fetched_data.disease_data:
                    raw_sources["guidelines_count"] = len(
                        fetched_data.disease_data.guideline_abstracts or []
                    )
            resp = QueryResponse(
                query_type=query_type,
                model_used=effective_model,
                response=DegradedResponse(
                    message="AI formatting is unavailable — no API key configured. Showing raw data from medical databases. Please add your API key in Settings.",
                    suggestion="Add your Anthropic or OpenAI API key in Settings to enable AI-formatted responses.",
                ),
                disclaimer=(
                    "This is unformatted data from external medical databases. "
                    "It has not been reviewed or formatted by AI. Use clinical judgment."
                ),
                latency_ms=latency_ms,
            )
            # Log to search history even for degraded responses
            if user and user.id:
                asyncio.create_task(
                    _log_search_history(user.id, request.query, query_type, {})
                )
            return resp
        raise

    raw_response2: str | None = None
    if raw_response:
        parsed = parse_llm_json(raw_response)
    else:
        parsed = None

    # Retry once if call failed or response unparseable
    if parsed is None:
        logger.info("First LLM call failed or unparseable, retrying...")
        await asyncio.sleep(settings.llm_retry_backoff_seconds)
        try:
            raw_response2 = await _call_llm(
                effective_model,
                prompt,
                max_tokens=max_tokens,
                user_key=user_llm_key,
                user_provider=user_llm_provider,
            )
        except HTTPException:
            raw_response2 = None
        if raw_response2:
            parsed = parse_llm_json(raw_response2)

    if parsed is None:
        latency_ms = int((time.time() - start_time) * 1000)
        # Distinguish: LLM never responded vs responded but JSON unparseable
        llm_never_responded = raw_response is None and raw_response2 is None
        if llm_never_responded:
            msg = "LLM call failed — please verify your API key is valid in Settings."
            sug = "Go to Settings → LLM API Key and check that your key is saved correctly."
        else:
            msg = (
                "Failed to parse AI response. The model returned an unexpected format."
            )
            sug = "Try rephrasing your query. If the problem persists, try a different query type."
        return QueryResponse(
            query_type=query_type,
            model_used=effective_model,
            response=DegradedResponse(message=msg, suggestion=sug),
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
        )

    # Pydantic + semantic validation
    validated_data, validation_warnings = _validate_response(parsed, query_type)
    if validated_data is None:
        latency_ms = int((time.time() - start_time) * 1000)
        return QueryResponse(
            query_type=query_type,
            model_used=effective_model,
            response=DegradedResponse(
                message="Response validation failed",
                suggestion="Try rephrasing your query",
            ),
            validation_warnings=validation_warnings,
            disclaimer=DISCLAIMER,
            latency_ms=latency_ms,
        )

    # Sparse response retry — if LLM returned critically sparse content, retry once with
    # an expansion instruction. Only for disease/drug/comparative types.
    if settings.retry_on_sparse_enabled and query_type in (
        "disease",
        "drug",
        "comparative",
        "evidence",
        "procedure",
    ):
        is_sparse, sparse_reasons = _is_critically_sparse(validated_data, query_type)
        if is_sparse:
            logger.info(
                "Response critically sparse (%s) — retrying with expansion instruction",
                sparse_reasons,
            )
            expansion_suffix = (
                "\n\nIMPORTANT: Your previous response was critically sparse. "
                "You MUST expand these sections: " + ", ".join(sparse_reasons) + ". "
                "Meet ALL minimum entry counts. Use the FULL token budget. Do NOT truncate."
            )
            try:
                raw_expansion = await _call_llm(
                    effective_model,
                    prompt + expansion_suffix,
                    max_tokens=max_tokens,
                    user_key=user_llm_key,
                    user_provider=user_llm_provider,
                )
                if raw_expansion:
                    parsed_expansion = parse_llm_json(raw_expansion)
                    if parsed_expansion:
                        v2, _ = _validate_response(parsed_expansion, query_type)
                        if v2 is not None:
                            validated_data = v2
            except Exception:
                logger.debug(
                    "Sparse retry failed — keeping original response", exc_info=True
                )

    # Enrich references with deterministic URLs (no LLM guessing)
    # Must run BEFORE citation validation so URL warnings reflect final values
    try:
        enrich_references(validated_data, fetched_data)
    except Exception:
        logger.warning(
            "URL enrichment failed — references will have no URLs", exc_info=True
        )

    # Citation validation
    citation_warnings = validate_citations(validated_data, query_type)
    validation_warnings.extend(citation_warnings)

    # Safety check
    safety_warnings = check_safety(request.query, validated_data, query_type)

    # Drug linker
    text_nodes = process_text_nodes(validated_data, query_type)

    # Build typed response
    model_cls = RESPONSE_MODELS[query_type]
    typed_response = model_cls.model_validate(validated_data)

    latency_ms = int((time.time() - start_time) * 1000)

    # Warn user when response is AI-generated rather than sourced from databases
    if prompt_mode == "generate":
        validation_warnings.append(
            "This response was generated by AI without data from medical databases. "
            "Verify claims against authoritative sources before clinical use."
        )

    response = QueryResponse(
        query_type=query_type,
        model_used=effective_model,
        response=typed_response,
        text_nodes=text_nodes,
        safety_warnings=safety_warnings,
        validation_warnings=validation_warnings,
        disclaimer=DISCLAIMER,
        cached=False,
        truncated=False,
        latency_ms=latency_ms,
    )

    # Cache write (Redis exact + semantic pgvector — both fire-and-forget, B4)
    cache_data = response.model_dump()
    asyncio.create_task(
        cache_set(redis_client, request.query, query_type, request.model_id, cache_data)
    )
    asyncio.create_task(
        semantic_cache_set(request.query, query_type, request.model_id, cache_data)
    )

    # Async log
    await _enqueue_log(
        {
            "query": request.query,
            "query_type": query_type,
            "model_used": request.model_id,
            "effective_model": effective_model,
            "prompt_mode": prompt_mode,
            "fetch_latency_ms": fetch_latency_ms,
            "response_json": cache_data,
            "latency_ms": latency_ms,
            "cached": False,
            "user_key_id": user_key_id,
        }
    )

    # Search history logging (fire-and-forget, non-blocking)
    if user and user.id:
        asyncio.create_task(
            _log_search_history(user.id, request.query, query_type, cache_data)
        )

    return response


async def _revalidate_semantic_cache(
    request,
    query_type: str,
    cache_id: int,
    redis_client,
    user_key_id,
    user_llm_key,
    user_llm_provider,
    user=None,
) -> None:
    """
    Background SWR revalidation: re-run the pipeline for a stale cache entry
    and update the semantic cache entry with the fresh response.
    Runs as a fire-and-forget asyncio task.
    """
    try:
        fresh_response = await process_query(
            request,
            redis_client=redis_client,
            user_key_id=user_key_id,
            user=user,
        )
        await semantic_cache_revalidate(cache_id, fresh_response.model_dump())
        logger.debug("SWR revalidation complete for semantic cache id=%d", cache_id)
    except Exception:
        logger.debug("SWR revalidation failed for cache id=%d", cache_id, exc_info=True)
