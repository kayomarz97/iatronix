"""LangChain-based embedding service using the user's BYOK provider key.

Supports OpenAI (text-embedding-3-small) and Google (text-embedding-004).
Anthropic has no embeddings API — vector search is skipped for those users.
"""

from __future__ import annotations

import logging
from typing import Optional

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
    if provider in ("openai", "openrouter"):
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=768,
            api_key=api_key,
        )
    if provider == "gemini":
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            return GoogleGenerativeAIEmbeddings(
                model="models/text-embedding-004",
                google_api_key=api_key,
            )
        except ImportError:
            logger.warning("langchain_google_genai not installed — skipping vector search for gemini users")
            return None
    if provider == "anthropic":
        if not voyage_api_key:
            logger.debug("Anthropic user has no Voyage AI key — vector search disabled")
            return None
        try:
            from langchain_voyageai import VoyageAIEmbeddings
            return VoyageAIEmbeddings(
                voyage_api_key=voyage_api_key,
                model="voyage-3",
                output_dimension=768,
            )
        except ImportError:
            logger.warning("langchain_voyageai not installed — vector search disabled for anthropic users")
            return None
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
