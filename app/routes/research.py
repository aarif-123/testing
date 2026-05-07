from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse
import uuid
import time
import json
from typing import Optional

from ..core.models import ConversationRequest
from ..core.auth import verify_api_key
from ..core.logging_config import log
from ..utils.ratelimit import check_rate_limit
from ..services.planning_service import plan_query
from ..services.research_service import research_service
from ..utils.cache import get_cache, cache_key

router = APIRouter(tags=["Research"])

@router.post("/api/research", dependencies=[Depends(verify_api_key)])
async def legacy_research(req: ConversationRequest, request: Request, background_tasks: BackgroundTasks):
    """Legacy endpoint for research requests."""
    t0 = time.time()
    rid = f"req_{uuid.uuid4().hex[:8]}"
    client_ip = request.client.host if request.client else "unknown"
    await check_rate_limit(client_ip)
    
    plan_t0 = time.time()
    plan = await plan_query(req.messages[-1].content)
    plan_ms = int((time.time() - plan_t0) * 1000)
    
    try:
        return await research_service.execute_plan(plan, req, rid, t0, plan_ms=plan_ms)
    except Exception as e:
        log.exception(f"Research failure: {e}")
        raise HTTPException(500, "Research execution failed")

@router.post("/api/chat", dependencies=[Depends(verify_api_key)])
async def chat_with_context(req: ConversationRequest, request: Request, background_tasks: BackgroundTasks):
    """
    Streaming research chat endpoint (SSE).

    SSE event types:
      - metadata: retrieval results (papers, chunks, plan info) — sent first
      - token:    one LLM token at a time
      - done:     final latency metrics
      - final:    used for fast routes (chitchat, compare, etc.) that don't stream
      - error:    on LLM failure
    """
    t0 = time.time()
    rid = f"req_{uuid.uuid4().hex[:8]}"
    client_ip = request.client.host if request.client else "unknown"
    await check_rate_limit(client_ip)

    # Generate Plan
    history = "\n".join([f"{m.role}: {m.content}" for m in req.messages[-3:]])
    plan_t0 = time.time()
    plan = await plan_query(req.messages[-1].content, history)
    plan_ms = int((time.time() - plan_t0) * 1000)

    # Cache hit — return immediately (no streaming needed)
    ck = cache_key("response", plan.cache_key_str, req.model_dump_json())
    cached = await get_cache("response", ck)
    if cached:
        return {**cached, "cached": True, "latency_ms": int((time.time() - t0) * 1000)}

    # Stream the response
    async def event_generator():
        try:
            async for chunk in research_service.execute_plan_stream(plan, req, rid, t0, plan_ms=plan_ms):
                yield chunk
        except Exception as e:
            log.error(f"Stream error [{rid}]: {e}")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


# ============================================================
# FILE UPLOAD + OCR
# ============================================================

@router.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    ingest_to_store_b: bool = Form(True),
):
    """
    Upload a PDF, image, or text file for OCR extraction.

    Pipeline:
      1. OCR / text extraction (PyMuPDF + Groq Vision for images)
      2. Store extracted text in Redis session (ephemeral, for chat context)
      3. [Optional] Ingest full text into Store B Supabase (permanent, searchable)
         - Chunks text with 150-char overlap
         - Embeds each chunk with BAAI/bge-base-en
         - Stores in arxiv_chunks for hybrid_search_arxiv
         - Deduplicates via chunk_hash

    Set ingest_to_store_b=false to skip permanent indexing (session-only mode).
    """
    from ..services.ocr_service import ocr_service
    from ..services.session_service import session_service
    from ..services.ingestion_service import ingest_pdf_to_store_b

    t0 = time.time()

    if not file.filename:
        raise HTTPException(400, "No filename provided")

    content_type = file.content_type or "application/octet-stream"
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(400, "Empty file")

    # Create session if not provided
    if not session_id:
        sess = await session_service.create_session()
        session_id = sess["session_id"]

    try:
        # ── Step 1: OCR ──────────────────────────────────────────
        ocr_result = await ocr_service.extract_text(
            file_bytes, file.filename, content_type
        )
        extracted_text = ocr_result["text"]
        ocr_ms = int((time.time() - t0) * 1000)

        # ── Step 2: Redis session storage ────────────────────────
        store_result = await session_service.store_paper(
            session_id=session_id,
            filename=file.filename,
            extracted_text=extracted_text,
            metadata={
                "method": ocr_result["method"],
                "pages": ocr_result.get("pages", 1),
                "original_size": len(file_bytes),
                "content_type": content_type,
            },
        )

        # ── Step 3: Store B ingestion ─────────────────────────────
        store_b_result = {"status": "skipped", "paper_id": None, "chunk_count": 0}
        if ingest_to_store_b and extracted_text.strip():
            ingest_t0 = time.time()
            store_b_result = await ingest_pdf_to_store_b(
                filename=file.filename,
                extracted_text=extracted_text,
                paper_metadata={},
            )
            store_b_result["ingest_ms"] = int((time.time() - ingest_t0) * 1000)
            log.info(
                f"[Upload] Store B ingestion: {store_b_result['status']} | "
                f"{store_b_result['chunk_count']} chunks"
            )

        total_ms = int((time.time() - t0) * 1000)
        return {
            "status": "success",
            "session_id": session_id,
            "filename": file.filename,
            "text_length": len(extracted_text),
            "text_preview": extracted_text[:500],
            "pages": ocr_result.get("pages", 1),
            "method": ocr_result["method"],
            # Session storage
            "stored_in_session": store_result.get("stored", False),
            "paper_id": store_result.get("id"),
            # Store B permanent indexing
            "store_b": {
                "status": store_b_result["status"],
                "paper_id": store_b_result.get("paper_id"),
                "chunk_count": store_b_result.get("chunk_count", 0),
                "ingest_ms": store_b_result.get("ingest_ms", 0),
            },
            "latency_ms": total_ms,
            "latency_breakdown": {
                "ocr_ms": ocr_ms,
                "total_ms": total_ms,
            },
        }

    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        log.exception(f"Upload failed: {e}")
        raise HTTPException(500, f"Upload processing failed: {str(e)}")


# ============================================================
# SESSION MANAGEMENT
# ============================================================

@router.post("/api/session/start")
async def start_session():
    """Create a new research session."""
    from ..services.session_service import session_service
    return await session_service.create_session()


@router.get("/api/session/{session_id}/papers")
async def get_session_papers(session_id: str):
    """List all papers uploaded in this session."""
    from ..services.session_service import session_service
    papers = await session_service.get_session_papers(session_id)
    return {"session_id": session_id, "papers": papers}


@router.post("/api/session/{session_id}/end")
async def end_session(session_id: str):
    """End a session and clean up all associated data."""
    from ..services.session_service import session_service
    return await session_service.end_session(session_id)

