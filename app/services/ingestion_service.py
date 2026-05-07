import hashlib
import uuid
from typing import Dict, Any, List
from ..core.logging_config import log
from .pool import pool
from .embedding import create_embedding

# ──────────────────────────────────────────────────────────────────
# Chunking helper
# ──────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> List[str]:
    """
    Split text into overlapping chunks for embedding.

    Uses a sliding window strategy:
    - chunk_size: target character length per chunk
    - overlap:    characters to repeat between consecutive chunks for context continuity
    """
    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start += chunk_size - overlap  # slide forward with overlap

    return chunks


def _chunk_hash(text: str) -> str:
    """Stable SHA-256 fingerprint for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────
# Ingest ArXiv paper (abstract-based, from MCP)
# ──────────────────────────────────────────────────────────────────

async def ingest_paper_to_store_b(paper: Dict[str, Any]) -> bool:
    """
    Background Task: Ingests a structured paper dictionary into Store B
    (ArXiv Supabase + Neo4j). Handles metadata, embeddings, and author relations.

    Input shape:
        {source_id, title, abstract, authors, published, url, categories, ...}
    """
    if not pool.store_b_ok:
        log.warning("Store B ingestion skipped: not operational.")
        return False

    try:
        source_id = paper.get("source_id")
        if not source_id:
            log.warning("Paper missing source_id, skipping ingestion.")
            return False

        # 1. Deduplication check (Supabase)
        res = await pool.arxiv_async_supabase.table("arxiv_papers") \
            .select("id") \
            .eq("source_id", source_id) \
            .execute()
        if res.data:
            log.info(f"Paper {source_id} already exists in Store B.")
            return True

        pid = paper.get("id") or str(uuid.uuid5(uuid.NAMESPACE_DNS, f"arxiv:{source_id}"))

        # 2. Metadata Upsert to arxiv_papers
        metadata = {
            "id": pid,
            "source_store": "arxiv",
            "source_id": source_id,
            "global_entity_id": paper.get("global_entity_id", f"arxiv:{source_id}"),
            "title": paper.get("title", "Unknown"),
            "abstract": paper.get("abstract", ""),
            "authors": paper.get("authors", []),
            "categories": paper.get("categories", []),
            "published": paper.get("published"),
            "url": paper.get("url"),
            "n_citation": paper.get("n_citation", 0),
        }
        await pool.arxiv_async_supabase.table("arxiv_papers").insert(metadata).execute()

        # 3. Authors Relation
        for author_name in paper.get("authors", []):
            try:
                normalized = author_name.lower().strip()
                res = await pool.arxiv_async_supabase.table("authors") \
                    .upsert(
                        {"name": author_name, "normalized_name": normalized},
                        on_conflict="normalized_name"
                    ).execute()
                if res.data:
                    author_id = res.data[0]["id"]
                    await pool.arxiv_async_supabase.table("paper_authors").upsert({
                        "paper_id": pid,
                        "author_id": author_id
                    }, on_conflict="paper_id,author_id").execute()
            except Exception as ae:
                log.warning(f"Author upsert failed ({author_name}): {ae}")

        # 4. Chunk abstract → embed → store in arxiv_chunks
        abstract = paper.get("abstract", "")
        if abstract:
            chunks = _chunk_text(abstract, chunk_size=1200, overlap=100)
            for i, chunk_text in enumerate(chunks):
                ch = _chunk_hash(chunk_text)
                try:
                    emb = await create_embedding(chunk_text)
                    chunk_data = {
                        "paper_id": pid,
                        "chunk_index": i,
                        "chunk": chunk_text,
                        "embedding": emb,
                        "embedding_model": "bge-base-en",
                        "section_type": "abstract",
                        "chunk_hash": ch,
                    }
                    await pool.arxiv_async_supabase.table("arxiv_chunks") \
                        .upsert(chunk_data, on_conflict="chunk_hash") \
                        .execute()
                except Exception as ce:
                    log.warning(f"Chunk {i} ingestion failed: {ce}")

        log.info(f"✅ Ingested to Store B: {paper.get('title')} [{source_id}]")
        return True

    except Exception as e:
        log.error(f"❌ Ingestion failed for {paper.get('title', '?')}: {e}")
        return False


# ──────────────────────────────────────────────────────────────────
# Ingest uploaded PDF text into Store B
# ──────────────────────────────────────────────────────────────────

async def ingest_pdf_to_store_b(
    filename: str,
    extracted_text: str,
    paper_metadata: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Ingest an uploaded PDF (already OCR-extracted) into Store B Supabase
    (arxiv_papers + arxiv_chunks).

    This makes the uploaded paper permanently searchable via hybrid_search_arxiv,
    enabling real-time RAG analysis on top of the full document content.

    Args:
        filename:        original filename (used as source_id if no DOI/arxiv_id)
        extracted_text:  full text from OCR pipeline
        paper_metadata:  optional dict with {title, authors, abstract, published, url}

    Returns:
        {paper_id, chunk_count, status, store_b_used}
    """
    if not pool.store_b_ok:
        log.warning("Store B unavailable — PDF indexed in session only (ephemeral).")
        return {"status": "store_b_unavailable", "paper_id": None, "chunk_count": 0, "store_b_used": False}

    meta = paper_metadata or {}
    # Derive a deterministic source_id from filename + content hash
    content_hash = hashlib.sha256(extracted_text[:5000].encode()).hexdigest()[:16]
    source_id = meta.get("arxiv_id") or meta.get("doi") or f"pdf:{content_hash}"
    pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"upload:{source_id}"))

    try:
        # ── 1. Deduplication ──────────────────────────────────────
        dedup = await pool.arxiv_async_supabase.table("arxiv_papers") \
            .select("id") \
            .eq("source_id", source_id) \
            .execute()

        if dedup.data:
            existing_id = dedup.data[0]["id"]
            log.info(f"PDF {filename} already in Store B (id={existing_id}). Skipping upsert.")
            # Count existing chunks
            chunks_res = await pool.arxiv_async_supabase.table("arxiv_chunks") \
                .select("id", count="exact") \
                .eq("paper_id", existing_id) \
                .execute()
            chunk_count = chunks_res.count or 0
            return {
                "status": "already_exists",
                "paper_id": existing_id,
                "chunk_count": chunk_count,
                "store_b_used": True,
            }

        # ── 2. Paper metadata row ─────────────────────────────────
        title = meta.get("title") or filename.replace(".pdf", "").replace("_", " ").title()
        abstract = meta.get("abstract") or extracted_text[:1500]

        paper_row = {
            "id": pid,
            "source_store": "upload",
            "source_id": source_id,
            "global_entity_id": f"upload:{source_id}",
            "title": title,
            "abstract": abstract,
            "authors": meta.get("authors", []),
            "categories": meta.get("categories", ["uploaded"]),
            "published": meta.get("published"),
            "url": meta.get("url"),
            "n_citation": 0,
        }
        await pool.arxiv_async_supabase.table("arxiv_papers").insert(paper_row).execute()
        log.info(f"[IngestPDF] Paper row created: {title} ({pid})")

        # ── 3. Chunking full text → embed → store ─────────────────
        chunks = _chunk_text(extracted_text, chunk_size=1000, overlap=150)
        log.info(f"[IngestPDF] Chunking: {len(chunks)} chunks from {len(extracted_text)} chars")

        ingested = 0
        failed = 0
        for i, chunk_text in enumerate(chunks):
            ch = _chunk_hash(chunk_text)
            try:
                emb = await create_embedding(chunk_text)

                # Label first chunk as abstract, rest as body
                section = "abstract" if i == 0 else "body"

                chunk_data = {
                    "paper_id": pid,
                    "chunk_index": i,
                    "chunk": chunk_text,
                    "embedding": emb,
                    "embedding_model": "bge-base-en",
                    "section_type": section,
                    "chunk_hash": ch,
                }
                await pool.arxiv_async_supabase.table("arxiv_chunks") \
                    .upsert(chunk_data, on_conflict="chunk_hash") \
                    .execute()
                ingested += 1

                # Progress log every 20 chunks
                if ingested % 20 == 0:
                    log.info(f"[IngestPDF] Progress: {ingested}/{len(chunks)} chunks ingested")

            except Exception as ce:
                log.warning(f"[IngestPDF] Chunk {i} failed: {ce}")
                failed += 1

        log.info(
            f"✅ [IngestPDF] Done: {title} | "
            f"{ingested} chunks ingested, {failed} failed | pid={pid}"
        )
        return {
            "status": "ingested",
            "paper_id": pid,
            "chunk_count": ingested,
            "failed_chunks": failed,
            "store_b_used": True,
            "source_id": source_id,
        }

    except Exception as e:
        log.error(f"❌ [IngestPDF] Pipeline failed for {filename}: {e}")
        return {
            "status": "error",
            "paper_id": None,
            "chunk_count": 0,
            "store_b_used": False,
            "error": str(e),
        }
