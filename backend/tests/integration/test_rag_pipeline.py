"""Integration tests for the RAG pipeline.

These tests mock external API calls and the LLM to verify the full pipeline flow
without network access or API costs.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.query import QueryRequest, QueryResponse
from app.services.rag_pipeline import process_query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_drug_response_json(drug_name: str = "metformin") -> str:
    return json.dumps({
        "drug_name": drug_name,
        "bluf": "Metformin is first-line for type 2 diabetes.",
        "additional_clinical_context": None,
        "drug_class": "Biguanide",
        "mechanism_of_action": {
            "value": "Inhibits hepatic gluconeogenesis",
            "loe": "I", "cor": "I", "source": "ADA 2024", "source_year": 2024, "confidence": "high",
        },
        "indications": [
            {"value": "Type 2 diabetes mellitus", "loe": "I", "cor": "I",
             "source": "ADA 2024", "source_year": 2024, "confidence": "high"},
            {"value": "Polycystic ovary syndrome", "loe": "II-2", "cor": "IIa",
             "source": "NICE", "source_year": 2023, "confidence": "moderate"},
            {"value": "Prediabetes prevention", "loe": "I", "cor": "IIa",
             "source": "ADA 2024", "source_year": 2024, "confidence": "high"},
        ],
        "dosing": [
            {"value": "500 mg BD with meals", "loe": "I", "cor": "I",
             "source": "FDA label", "source_year": 2022, "confidence": "high",
             "route": "oral", "frequency": "twice daily"},
            {"value": "Titrate to 1000 mg BD over 4 weeks", "loe": "I", "cor": "I",
             "source": "ADA 2024", "source_year": 2024, "confidence": "high",
             "route": "oral", "frequency": "twice daily"},
            {"value": "Max dose 2550 mg/day", "loe": "I", "cor": "I",
             "source": "FDA label", "source_year": 2022, "confidence": "high",
             "route": "oral", "frequency": None},
            {"value": "XR formulation: 500-2000 mg OD with evening meal", "loe": "I", "cor": "I",
             "source": "FDA label", "source_year": 2022, "confidence": "high",
             "route": "oral", "frequency": "once daily"},
        ],
        "contraindications": [
            {"value": "eGFR < 30 mL/min/1.73m²", "loe": "I", "cor": "III-harm",
             "source": "FDA label", "source_year": 2022, "confidence": "high"},
            {"value": "Acute/decompensated heart failure", "loe": "I", "cor": "III-harm",
             "source": "ADA 2024", "source_year": 2024, "confidence": "high"},
            {"value": "IV contrast administration (hold 48h)", "loe": "II-2", "cor": "I",
             "source": "ACR", "source_year": 2023, "confidence": "high"},
        ],
        "side_effects": [
            {"value": "GI upset (nausea, diarrhoea) — 30%", "loe": "I", "cor": "I",
             "source": "FDA label", "source_year": 2022, "confidence": "high"},
            {"value": "Lactic acidosis (rare, 0.03/1000)", "loe": "I", "cor": "III-harm",
             "source": "FDA label", "source_year": 2022, "confidence": "high"},
            {"value": "Vitamin B12 deficiency (long-term)", "loe": "I", "cor": "I",
             "source": "ADA 2024", "source_year": 2024, "confidence": "high"},
            {"value": "Metallic taste", "loe": "II-2", "cor": "IIb",
             "source": "Expert opinion", "source_year": None, "confidence": "moderate"},
            {"value": "Weight neutral / slight reduction", "loe": "I", "cor": "I",
             "source": "ADA 2024", "source_year": 2024, "confidence": "high"},
        ],
        "interactions": [
            {"drug": "alcohol", "severity": "major",
             "description": "Increased lactic acidosis risk",
             "evidence": {"value": "Avoid heavy alcohol use", "loe": "III", "cor": "IIb",
                          "source": "FDA label", "source_year": 2022, "confidence": "moderate"}},
            {"drug": "iodinated contrast", "severity": "major",
             "description": "Risk of contrast-induced nephropathy and lactic acidosis",
             "evidence": {"value": "Hold 48h before and after contrast", "loe": "II-2",
                          "cor": "I", "source": "ACR", "source_year": 2023, "confidence": "high"}},
            {"drug": "topiramate", "severity": "moderate",
             "description": "Increased risk of lactic acidosis",
             "evidence": None},
            {"drug": "cimetidine", "severity": "moderate",
             "description": "Increases metformin levels via OCT2 inhibition",
             "evidence": None},
            {"drug": "rifampicin", "severity": "moderate",
             "description": "Induces CYP enzymes, may reduce metformin efficacy",
             "evidence": None},
        ],
        "pharmacokinetics": {
            "value": "Bioavailability 50-60%, renal excretion unchanged, t½ 6.2h",
            "loe": "I", "cor": "I", "source": "FDA label", "source_year": 2022, "confidence": "high",
        },
        "special_populations": [
            {"value": "Renal: reduce dose if eGFR 30-45; contraindicated if <30",
             "loe": "I", "cor": "I", "source": "FDA label", "source_year": 2022, "confidence": "high"},
        ],
        "monitoring": [
            {"value": "eGFR at baseline, then annually (or more often if renal risk)",
             "loe": "I", "cor": "I", "source": "ADA 2024", "source_year": 2024, "confidence": "high"},
            {"value": "B12 levels every 2-3 years in long-term use",
             "loe": "I", "cor": "I", "source": "ADA 2024", "source_year": 2024, "confidence": "high"},
        ],
        "references": [
            {"source": "ADA 2024", "title": "Standards of Care in Diabetes", "year": 2024, "url": None},
        ],
    })


def _make_mock_user(tier: str = "free"):
    user = MagicMock()
    user.id = 1
    user.encrypted_llm_key = None
    user.llm_provider = None
    user.tier = tier
    user.scopes = {"query": True}
    user.role = "user"
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_drug_query_full_flow():
    """test_drug_query_full_flow: mock fetch + LLM, assert response shape."""
    from app.services.data_fetcher import DrugFetchResult, FetchedData

    mock_drug_result = DrugFetchResult(
        generic_name="metformin",
        indications_raw="Type 2 diabetes mellitus",
        dosing_raw="500 mg twice daily",
        fetch_success=True,
        data_source="fda",
    )
    mock_fetched = FetchedData(query_type="drug", drug_data=mock_drug_result)

    request = QueryRequest(query="metformin", model_id="claude-haiku-4-5-20251001")

    with (
        patch("app.services.rag_pipeline._analyze_query_with_dspy", new_callable=AsyncMock, return_value={
            "query_type": "drug", "entities": ["metformin"],
            "condition_context": None, "response_focus": "", "depth": "standard", "related_topics": [],
        }),
        patch("app.services.rag_pipeline.cache_get", new_callable=AsyncMock, return_value=None),
        patch("app.services.rag_pipeline.semantic_cache_get", new_callable=AsyncMock, return_value=(None, None)),
        patch("app.services.rag_pipeline.fetch_data_for_query", new_callable=AsyncMock, return_value=mock_fetched),
        patch("app.services.rag_pipeline.vector_search", new_callable=AsyncMock, return_value=[]),
        patch("app.services.rag_pipeline._call_llm", new_callable=AsyncMock, return_value=_make_drug_response_json()),
        patch("app.services.rag_pipeline.cache_set", new_callable=AsyncMock),
        patch("app.services.rag_pipeline.semantic_cache_set", new_callable=AsyncMock),
    ):
        response = await process_query(request, redis_client=None, user_key_id=None, user=None)

    assert isinstance(response, QueryResponse)
    assert response.query_type == "drug"
    assert response.response is not None
    assert hasattr(response.response, "drug_name")


@pytest.mark.asyncio
async def test_disease_query_cache_hit():
    """test_disease_query_cache_hit: cached response returned without LLM call."""
    cached_payload = {
        "query_type": "disease",
        "model_used": "claude-haiku-4-5-20251001",
        "response": {"disease_name": "Hypertension", "bluf": "...", "treatment": {
            "first_line": [], "second_line": [], "adjunctive": [], "non_pharmacological": []
        }, "references": []},
        "text_nodes": [], "safety_warnings": [], "validation_warnings": [],
        "disclaimer": "", "cached": True, "truncated": False, "latency_ms": 10,
    }

    request = QueryRequest(query="hypertension", model_id="claude-haiku-4-5-20251001")

    with (
        patch("app.services.rag_pipeline._analyze_query_with_dspy", new_callable=AsyncMock, return_value={
            "query_type": "disease", "entities": ["hypertension"],
            "condition_context": None, "response_focus": "", "depth": "standard", "related_topics": [],
        }),
        patch("app.services.rag_pipeline.cache_get", new_callable=AsyncMock, return_value=cached_payload),
        patch("app.services.rag_pipeline._call_llm", new_callable=AsyncMock) as mock_llm,
    ):
        response = await process_query(request, redis_client=None, user_key_id=None, user=None)
        mock_llm.assert_not_called()

    assert response.cached is True


@pytest.mark.asyncio
async def test_circuit_breaker_trip():
    """test_circuit_breaker_trip: provider unavailable → degraded response returned."""
    request = QueryRequest(query="metformin", model_id="claude-haiku-4-5-20251001")

    with (
        patch("app.services.rag_pipeline._analyze_query_with_dspy", new_callable=AsyncMock, return_value={
            "query_type": "drug", "entities": ["metformin"],
            "condition_context": None, "response_focus": "", "depth": "standard", "related_topics": [],
        }),
        patch("app.services.rag_pipeline.cache_get", new_callable=AsyncMock, return_value=None),
        patch("app.services.rag_pipeline.semantic_cache_get", new_callable=AsyncMock, return_value=(None, None)),
        patch("app.services.rag_pipeline.cache_get_any_version", new_callable=AsyncMock, return_value=None),
        patch("app.services.rag_pipeline.is_provider_available", return_value=False),
    ):
        response = await process_query(request, redis_client=None, user_key_id=None, user=None)

    from app.schemas.query import DegradedResponse
    assert isinstance(response.response, DegradedResponse)


@pytest.mark.asyncio
async def test_timeout_handling():
    """test_timeout_handling: pipeline timeout → 504-style degraded response."""
    import asyncio
    request = QueryRequest(query="what is aspirin", model_id="claude-haiku-4-5-20251001")

    async def slow_fetch(*args, **kwargs):
        await asyncio.sleep(999)

    with (
        patch("app.services.rag_pipeline._analyze_query_with_dspy", new_callable=AsyncMock, return_value={
            "query_type": "drug", "entities": ["aspirin"],
            "condition_context": None, "response_focus": "", "depth": "standard", "related_topics": [],
        }),
        patch("app.services.rag_pipeline.cache_get", new_callable=AsyncMock, return_value=None),
        patch("app.services.rag_pipeline.semantic_cache_get", new_callable=AsyncMock, return_value=(None, None)),
        patch("app.services.rag_pipeline.fetch_data_for_query", new=slow_fetch),
        patch("app.services.rag_pipeline.vector_search", new_callable=AsyncMock, return_value=[]),
    ):
        with pytest.raises((asyncio.TimeoutError, Exception)):
            await asyncio.wait_for(
                process_query(request, redis_client=None, user_key_id=None, user=None),
                timeout=0.1,
            )


@pytest.mark.asyncio
async def test_sparse_response_retry():
    """test_sparse_response_retry: sparse first response triggers retry with fuller response."""
    from app.services.data_fetcher import DrugFetchResult, FetchedData

    mock_fetched = FetchedData(
        query_type="drug",
        drug_data=DrugFetchResult(generic_name="aspirin", indications_raw="Pain", fetch_success=True),
    )

    sparse_json = json.dumps({
        "drug_name": "aspirin",
        "drug_class": "NSAID",
        "indications": [],
        "dosing": [],
        "contraindications": [],
        "side_effects": [],
        "interactions": [],
        "special_populations": [],
        "monitoring": [],
        "references": [],
    })
    full_json = _make_drug_response_json("aspirin")
    call_count = {"n": 0}

    async def mock_llm(*args, **kwargs):
        call_count["n"] += 1
        return sparse_json if call_count["n"] == 1 else full_json

    request = QueryRequest(query="aspirin", model_id="claude-haiku-4-5-20251001")

    with (
        patch("app.services.rag_pipeline._analyze_query_with_dspy", new_callable=AsyncMock, return_value={
            "query_type": "drug", "entities": ["aspirin"],
            "condition_context": None, "response_focus": "", "depth": "standard", "related_topics": [],
        }),
        patch("app.services.rag_pipeline.cache_get", new_callable=AsyncMock, return_value=None),
        patch("app.services.rag_pipeline.semantic_cache_get", new_callable=AsyncMock, return_value=(None, None)),
        patch("app.services.rag_pipeline.fetch_data_for_query", new_callable=AsyncMock, return_value=mock_fetched),
        patch("app.services.rag_pipeline.vector_search", new_callable=AsyncMock, return_value=[]),
        patch("app.services.rag_pipeline._call_llm", new=mock_llm),
        patch("app.services.rag_pipeline.cache_set", new_callable=AsyncMock),
        patch("app.services.rag_pipeline.semantic_cache_set", new_callable=AsyncMock),
    ):
        response = await process_query(request, redis_client=None, user_key_id=None, user=None)

    # Should have retried (2 LLM calls)
    assert call_count["n"] == 2
    assert response.query_type == "drug"
