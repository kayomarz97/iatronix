"""Cost estimation utilities — shown to users before LLM operations."""

import math
from app.config import settings


def estimate_pdf_ingestion(text: str) -> dict:
    """Estimate scope of ingesting a PDF.

    PDF ingestion uses local sentence-transformers (free, no API cost).
    This function returns scope info so the user knows what they're uploading.
    """
    word_count = len(text.split())
    char_count = len(text)
    estimated_tokens = int(word_count * 1.33)
    chunks = max(1, math.ceil(char_count / settings.chunk_size))

    return {
        "word_count": word_count,
        "char_count": char_count,
        "estimated_tokens": estimated_tokens,
        "chunks": chunks,
        "api_cost_usd": 0.0,
        "note": (
            f"PDF will be split into ~{chunks} searchable chunks. "
            "Embeddings use a free local model — no API tokens are consumed for upload."
        ),
    }


def estimate_query_cost(query_type: str, fetched_data_chars: int = 8000) -> dict:
    """Estimate per-query LLM cost for the user's awareness."""
    if query_type == "drug":
        model_name = "Haiku"
        model_id = settings.model_haiku
        input_rate = settings.cost_haiku_input_per_m
        output_rate = settings.cost_haiku_output_per_m
        max_out = settings.llm_max_tokens_format
    else:
        model_name = "Haiku"
        model_id = settings.model_haiku
        input_rate = settings.cost_haiku_input_per_m
        output_rate = settings.cost_haiku_output_per_m
        max_out = settings.llm_max_tokens_format_disease

    est_input = (
        int(fetched_data_chars / 4) + 500
    )  # fetched data + system prompt overhead
    est_output = max_out  # worst case

    cost = (est_input / 1_000_000 * input_rate) + (est_output / 1_000_000 * output_rate)

    return {
        "model": model_name,
        "model_id": model_id,
        "estimated_input_tokens": est_input,
        "estimated_output_tokens": est_output,
        "estimated_cost_usd": round(cost, 6),
        "note": "Actual cost varies with API provider pricing and exact response length.",
    }
