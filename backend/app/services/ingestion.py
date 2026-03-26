"""Document ingestion: PDF upload, PMC full-text, StatPearls, PubMed abstracts.

Chunks text, embeds with local model, stores in pgvector.
All embedding is free (local all-MiniLM-L6-v2).
"""

import asyncio
import io
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from xml.etree import ElementTree

import httpx
import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select

from app.config import settings
from app.db.session import async_session as async_session_factory
from app.models.document import Document, DocumentChunk
from app.services.embedder import Embedder
from app.services.pdf_verifier import verify_pdf
from app.services import r2_storage

logger = logging.getLogger(__name__)

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
    separators=["\n\n", "\n", ". ", " "],
)

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


# ---------------------------------------------------------------------------
# PDF Ingestion
# ---------------------------------------------------------------------------


async def ingest_pdf(
    file_name: str,
    file_bytes: bytes,
    user_id: Optional[int] = None,
) -> Document:
    """Extract text from PDF, chunk, embed, store, and optionally upload to R2."""
    pages = await asyncio.to_thread(_extract_pdf_pages, file_bytes)
    page_count = len(pages)
    title = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    # Auto-verify
    verified, publisher = await asyncio.to_thread(verify_pdf, file_bytes)

    # Upload to Cloudflare R2 if configured
    r2_key = None
    r2_url = None
    r2_key_candidate = f"documents/{user_id or 'anon'}/{uuid.uuid4().hex}/{file_name}"
    if r2_storage.is_configured():
        try:
            r2_url = await r2_storage.upload_pdf(
                file_bytes,
                r2_key_candidate,
                metadata={"user_id": str(user_id or ""), "verified": str(verified)},
            )
            r2_key = r2_key_candidate
        except Exception as e:
            logger.warning(f"R2 upload failed: {e} — continuing without cloud storage")
            r2_url = None
            r2_key = None

    # Set expiry for non-approved documents
    expires_at = (
        None
        if verified
        else (
            datetime.now(timezone.utc)
            + timedelta(hours=settings.pdf_non_approved_ttl_hours)
        )
    )

    # Chunk with page tracking
    chunks = _chunk_pages(pages)

    # Embed in batches
    embedder = Embedder.get_instance()
    texts = [c["text"] for c in chunks]
    embeddings = await asyncio.to_thread(embedder.embed_texts, texts)

    # Store
    async with async_session_factory() as session:
        doc = Document(
            title=title,
            source_type="pdf",
            file_name=file_name,
            pdf_size_bytes=len(file_bytes),
            page_count=page_count,
            uploaded_by_user_id=user_id,
            verified=verified,
            publisher=publisher,
            r2_key=r2_key,
            r2_url=r2_url,
            expires_at=expires_at,
        )
        session.add(doc)
        await session.flush()  # get doc.id

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            session.add(
                DocumentChunk(
                    document_id=doc.id,
                    content=chunk["text"],
                    chunk_index=i,
                    page_number=chunk.get("page_number"),
                    embedding=emb,
                )
            )

        await session.commit()
        await session.refresh(doc)
        doc._chunk_count = len(chunks)
        return doc


async def get_pdf_text_preview(file_bytes: bytes) -> tuple[str, int]:
    """Extract text from PDF for cost estimation — does NOT store anything.
    Returns (full_text, page_count).
    """
    pages = await asyncio.to_thread(_extract_pdf_pages, file_bytes)
    full_text = " ".join(text for _, text in pages)
    return full_text, len(pages)


def _extract_pdf_pages(file_bytes: bytes) -> list[tuple[int, str]]:
    """Extract (page_number, text) from each PDF page."""
    pages = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((i, text))
    return pages


def _chunk_pages(pages: list[tuple[int, str]]) -> list[dict]:
    """Chunk page text with page number tracking."""
    chunks = []
    for page_num, text in pages:
        page_chunks = _splitter.split_text(text)
        for chunk_text in page_chunks:
            if chunk_text.strip():
                chunks.append({"text": chunk_text, "page_number": page_num})
    return chunks


# ---------------------------------------------------------------------------
# PMC Full-Text Ingestion
# ---------------------------------------------------------------------------


async def ingest_pmc_article(pmcid: str) -> Optional[Document]:
    """Fetch and index a full-text PMC article."""
    async with async_session_factory() as session:
        existing = await session.execute(
            select(Document).where(Document.pmcid == pmcid)
        )
        if existing.scalar_one_or_none():
            return None  # already indexed

    # Fetch full text XML
    async with httpx.AsyncClient(timeout=15.0) as client:
        params = {"db": "pmc", "id": pmcid, "rettype": "xml"}
        if settings.pubmed_api_key:
            params["api_key"] = settings.pubmed_api_key
        resp = await client.get(f"{NCBI_BASE}/efetch.fcgi", params=params)
        if resp.status_code != 200:
            return None

    sections = _parse_pmc_xml(resp.text)
    if not sections:
        return None

    title = sections.pop("_title", pmcid)

    # Chunk sections
    chunks = []
    for section_name, text in sections.items():
        section_chunks = _splitter.split_text(text)
        for chunk_text in section_chunks:
            if chunk_text.strip():
                chunks.append(
                    {
                        "text": chunk_text,
                        "page_number": None,
                        "section": section_name,
                    }
                )

    if not chunks:
        return None

    # Embed
    embedder = Embedder.get_instance()
    texts = [c["text"] for c in chunks]
    embeddings = await asyncio.to_thread(embedder.embed_texts, texts)

    # Store
    async with async_session_factory() as session:
        doc = Document(
            title=title,
            source_type="pmc",
            pmcid=pmcid,
            verified=True,
            publisher="PubMed Central",
        )
        session.add(doc)
        await session.flush()

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            session.add(
                DocumentChunk(
                    document_id=doc.id,
                    content=chunk["text"],
                    chunk_index=i,
                    embedding=emb,
                    metadata_={"section": chunk.get("section")},
                )
            )

        await session.commit()
        await session.refresh(doc)
        return doc


def _parse_pmc_xml(xml_text: str) -> dict[str, str]:
    """Parse PMC XML into {section_name: text} dict."""
    sections = {}
    try:
        root = ElementTree.fromstring(xml_text)
        # Title
        title_el = root.find(".//article-title")
        if title_el is not None and title_el.text:
            sections["_title"] = title_el.text.strip()

        # Abstract
        abstract_parts = []
        for ab in root.findall(".//abstract//p"):
            text = "".join(ab.itertext()).strip()
            if text:
                abstract_parts.append(text)
        if abstract_parts:
            sections["Abstract"] = "\n".join(abstract_parts)

        # Body sections
        for sec in root.findall(".//body//sec"):
            sec_title_el = sec.find("title")
            sec_title = (
                sec_title_el.text.strip()
                if sec_title_el is not None and sec_title_el.text
                else "Untitled"
            )
            paragraphs = []
            for p in sec.findall(".//p"):
                text = "".join(p.itertext()).strip()
                if text:
                    paragraphs.append(text)
            if paragraphs:
                sections[sec_title] = "\n".join(paragraphs)

    except Exception:
        logger.debug("PMC XML parsing failed", exc_info=True)

    return sections


# ---------------------------------------------------------------------------
# StatPearls Ingestion
# ---------------------------------------------------------------------------


async def ingest_statpearls(topic: str) -> Optional[Document]:
    """Fetch and index a StatPearls monograph from NCBI Bookshelf."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Search for StatPearls article on this topic
        params = {
            "db": "books",
            "term": f"statpearls[book] {topic}",
            "retmax": 1,
        }
        if settings.pubmed_api_key:
            params["api_key"] = settings.pubmed_api_key
        resp = await client.get(f"{NCBI_BASE}/esearch.fcgi", params=params)
        if resp.status_code != 200:
            return None

        # Extract ID
        match = re.search(r"<Id>(\d+)</Id>", resp.text)
        if not match:
            return None
        book_id = match.group(1)

        # Check if already indexed
        async with async_session_factory() as session:
            existing = await session.execute(
                select(Document).where(
                    Document.source_type == "statpearls",
                    Document.pmid == book_id,
                )
            )
            if existing.scalar_one_or_none():
                return None

        # Fetch full text
        fetch_params = {"db": "books", "id": book_id, "rettype": "xml"}
        if settings.pubmed_api_key:
            fetch_params["api_key"] = settings.pubmed_api_key
        resp = await client.get(f"{NCBI_BASE}/efetch.fcgi", params=fetch_params)
        if resp.status_code != 200:
            return None

    # Parse sections
    sections = _parse_statpearls_xml(resp.text)
    if not sections:
        return None

    title = sections.pop("_title", f"StatPearls: {topic}")

    # Chunk
    chunks = []
    for section_name, text in sections.items():
        section_chunks = _splitter.split_text(text)
        for chunk_text in section_chunks:
            if chunk_text.strip():
                chunks.append(
                    {
                        "text": chunk_text,
                        "section": section_name,
                    }
                )

    if not chunks:
        return None

    # Embed and store
    embedder = Embedder.get_instance()
    texts = [c["text"] for c in chunks]
    embeddings = await asyncio.to_thread(embedder.embed_texts, texts)

    async with async_session_factory() as session:
        doc = Document(
            title=title,
            source_type="statpearls",
            pmid=book_id,
            verified=True,
            publisher="StatPearls / NCBI Bookshelf",
        )
        session.add(doc)
        await session.flush()

        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            session.add(
                DocumentChunk(
                    document_id=doc.id,
                    content=chunk["text"],
                    chunk_index=i,
                    embedding=emb,
                    metadata_={"section": chunk.get("section")},
                )
            )

        await session.commit()
        await session.refresh(doc)
        return doc


def _parse_statpearls_xml(xml_text: str) -> dict[str, str]:
    """Parse StatPearls/Bookshelf XML into sections."""
    sections = {}
    try:
        root = ElementTree.fromstring(xml_text)

        title_el = root.find(".//book-part-meta/title-group/title")
        if title_el is not None:
            sections["_title"] = "".join(title_el.itertext()).strip()

        for sec in root.findall(".//sec"):
            title_el = sec.find("title")
            sec_title = (
                "".join(title_el.itertext()).strip()
                if title_el is not None
                else "Untitled"
            )
            paragraphs = []
            for p in sec.findall("p"):
                text = "".join(p.itertext()).strip()
                if text:
                    paragraphs.append(text)
            if paragraphs:
                sections[sec_title] = "\n".join(paragraphs)

    except Exception:
        logger.debug("StatPearls XML parsing failed", exc_info=True)

    return sections


# ---------------------------------------------------------------------------
# PubMed Abstract Ingestion (fallback)
# ---------------------------------------------------------------------------


async def ingest_pubmed_abstracts(abstracts: list[dict]) -> int:
    """Index PubMed abstracts into pgvector. Deduplicates by PMID.

    Each abstract dict should have: pmid, title, abstract, year, journal.
    Returns count of newly indexed abstracts.
    """
    if not abstracts:
        return 0

    indexed = 0
    embedder = Embedder.get_instance()

    async with async_session_factory() as session:
        for ab in abstracts:
            pmid = str(ab.get("pmid", ""))
            if not pmid:
                continue

            # Check if already indexed
            existing = await session.execute(
                select(Document.id).where(Document.pmid == pmid)
            )
            if existing.scalar_one_or_none():
                continue

            text = ab.get("abstract", "") or ab.get("title", "")
            if not text.strip():
                continue

            embedding = await asyncio.to_thread(embedder.embed_text, text)

            doc = Document(
                title=ab.get("title", f"PMID:{pmid}"),
                source_type="pubmed",
                pmid=pmid,
                verified=True,
                publisher=ab.get("journal", "PubMed"),
            )
            session.add(doc)
            await session.flush()

            session.add(
                DocumentChunk(
                    document_id=doc.id,
                    content=text,
                    chunk_index=0,
                    embedding=embedding,
                    metadata_={"year": ab.get("year"), "journal": ab.get("journal")},
                )
            )
            indexed += 1

        await session.commit()

    return indexed
