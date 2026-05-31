"""LangChain-based embedding service using the user's BYOK provider key.

Embedding model per provider comes from the registry (config/providers.yaml)
— e.g. OpenAI text-embedding-3-small, Google gemini-embedding-001 (the old
text-embedding-004 was shut down 2026-01-14), Anthropic via Voyage. Providers
whose registry embedding_model is null (Cerebras/xAI/OpenRouter) have no
embeddings and return None.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.services.provider_registry import get_registry

logger = logging.getLogger(__name__)


def get_langchain_embedder(
    provider: str,
    api_key: str,
    voyage_api_key: Optional[str] = None,
):
    """Return a LangChain embedder for the given provider, or None if unsupported.

    Anthropic users can optionally provide a Voyage AI key (free tier, 200M tokens/month)
    to enable vector search. Without it, vector search is skipped for Anthropic users.
    """
    reg = get_registry()
    model = reg.embedding_model(provider)
    if not model:
        return None
    client_kind = (reg.provider_meta(provider) or {}).get("client_kind", "openai_compatible")

    # Anthropic -> Voyage (BYO Voyage key, separate from the LLM key)
    if provider == "anthropic":
        if not voyage_api_key:
            logger.debug("Anthropic user has no Voyage AI key — vector search disabled")
            return None
        try:
            from langchain_voyageai import VoyageAIEmbeddings
            return VoyageAIEmbeddings(
                voyage_api_key=voyage_api_key,
                model=model,
                output_dimension=768,
            )
        except ImportError:
            logger.warning("langchain_voyageai not installed — vector search disabled for anthropic users")
            return None

    if client_kind == "google_genai":
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            return GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=api_key,
            )
        except ImportError:
            logger.warning("langchain_google_genai not installed — skipping vector search for gemini users")
            return None

    if client_kind == "openai_compatible":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=model,
            dimensions=768,
            api_key=api_key,
        )

    return None


async def embed_query(
    query: str,
    provider: str,
    api_key: str,
    voyage_api_key: Optional[str] = None,
) -> Optional[list[float]]:
    """Embed a query string. Returns None if the provider has no embeddings support."""
    embedder = get_langchain_embedder(provider, api_key, voyage_api_key)
    if embedder is None:
        return None
    try:
        return await embedder.aembed_query(query)
    except Exception as e:
        logger.warning("Embedding failed (%s): %s", provider, e)
        return None


async def embed_texts(
    texts: list[str],
    provider: str,
    api_key: str,
    voyage_api_key: Optional[str] = None,
) -> Optional[list[list[float]]]:
    """Embed a batch of texts. Returns None if unsupported."""
    embedder = get_langchain_embedder(provider, api_key, voyage_api_key)
    if embedder is None:
        return None
    try:
        return await embedder.aembed_documents(texts)
    except Exception as e:
        logger.warning("Batch embedding failed (%s): %s", provider, e)
        return None
