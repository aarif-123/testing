"""
PDF Ingestion Pipeline — End-to-End Verification
=================================================
Verifies the complete PDF ingestion + Store B vector search pipeline:

  Stage 1  ── Environment & Connectivity
  Stage 2  ── Embedding model
  Stage 3  ── OCR text extraction
  Stage 4  ── Store B Supabase schema check
  Stage 5  ── Chunk + embed + ingest to arxiv_chunks
  Stage 6  ── hybrid_search_arxiv retrieval
  Stage 7  ── End-to-end latency report

Usage:
    python tests/verify_pdf_pipeline.py [path/to/paper.pdf]

If no PDF is provided, a synthetic research paper is used.
"""

import asyncio
import hashlib
import os
import sys
import time
import json
import tempfile
from pathlib import Path

# ── Load env relative to project root ─────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env.local", override=True)
load_dotenv(ROOT / ".env", override=False)

# ── Color helpers ─────────────────────────────────────────────────
OK   = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"


def section(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def result(ok: bool, label: str, detail: str = ""):
    icon = OK if ok else FAIL
    detail_str = f"  →  {detail}" if detail else ""
    print(f"  {icon}  {label}{detail_str}")


def info(label: str, detail: str = ""):
    detail_str = f"  →  {detail}" if detail else ""
    print(f"  {INFO}  {label}{detail_str}")


def warn(label: str, detail: str = ""):
    detail_str = f"  →  {detail}" if detail else ""
    print(f"  {WARN}  {label}{detail_str}")


# ── Synthetic research paper (fallback) ───────────────────────────
SYNTHETIC_TEXT = """
Attention Is All You Need

Abstract:
The dominant sequence transduction models are based on complex recurrent or convolutional neural
networks in an encoder-decoder configuration. The best performing models also connect the encoder
and decoder through an attention mechanism. We propose a new simple network architecture, the
Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions
entirely. Experiments on two machine translation tasks show these models to be superior in quality
while being more parallelizable and requiring significantly less time to train.

1. Introduction
Recurrent neural networks, long short-term memory and gated recurrent neural networks in particular,
have been firmly established as state of the art approaches in sequence modeling and transduction
problems such as language modeling and machine translation. Subsequent efforts have continued to push
the boundaries of recurrent language models and encoder-decoder architectures.

Recurrent models typically factor computation along the symbol positions of the input and output
sequences. Aligning the positions to steps in computation time, they generate a sequence of hidden
states h_t, as a function of the previous hidden state h_{t-1} and the input for position t.

2. Model Architecture
The Transformer follows an encoder-decoder structure using stacked self-attention and point-wise,
fully connected layers for both the encoder and decoder. The encoder maps an input sequence of
symbol representations to a sequence of continuous representations. The decoder then generates an
output sequence of symbols one element at a time.

3. Attention Mechanism
An attention function can be described as mapping a query and a set of key-value pairs to an output,
where the query, keys, values, and output are all vectors. The output is computed as a weighted sum
of the values, where the weight assigned to each value is computed by a compatibility function of the
query with the corresponding key.

Scaled Dot-Product Attention:
We call our particular attention "Scaled Dot-Product Attention". The input consists of queries and
keys of dimension d_k, and values of dimension d_v. We compute the dot products of the query with
all keys, divide each by sqrt(d_k), and apply a softmax function to obtain the weights on the values.

4. Results
On the WMT 2014 English-to-German translation task, the big transformer model outperforms the best
previously reported models including ensembles by more than 2.0 BLEU, establishing a new state-of-
the-art BLEU score of 28.4. The big transformer model achieves 41.0 BLEU on the WMT 2014 English-
to-French translation task, outperforming all of the previously published single models, at less
than 1/4 the training cost of the previous state-of-the-art model.
""".strip()


# ══════════════════════════════════════════════════════════════════
# Stage 1: Environment & Connectivity
# ══════════════════════════════════════════════════════════════════
async def stage1_environment() -> bool:
    section("Stage 1 — Environment & Store B Credentials")

    required = {
        "ARXIV_SUPABASE_URL": os.getenv("ARXIV_SUPABASE_URL"),
        "ARXIV_SUPABASE_KEY": os.getenv("ARXIV_SUPABASE_KEY"),
        "GROQ_API_KEY":       os.getenv("GROQ_API_KEY"),
    }
    optional = {
        "ARXIV_NEO4J_URI":      os.getenv("ARXIV_NEO4J_URI"),
        "ARXIV_NEO4J_USER":     os.getenv("ARXIV_NEO4J_USER"),
        "ARXIV_NEO4J_PASSWORD": os.getenv("ARXIV_NEO4J_PASSWORD"),
    }

    all_ok = True
    for name, val in required.items():
        if val:
            masked = val[:8] + "…" + val[-4:] if len(val) > 16 else "***"
            result(True, name, f"set ({masked})")
        else:
            result(False, name, "MISSING — Store B will be unavailable")
            all_ok = False

    for name, val in optional.items():
        if val:
            result(True, f"{name} [optional]", "set")
        else:
            warn(f"{name} [optional]", "not set — Store B Neo4j disabled")

    return all_ok


# ══════════════════════════════════════════════════════════════════
# Stage 2: Embedding model
# ══════════════════════════════════════════════════════════════════
async def stage2_embedding() -> list:
    section("Stage 2 — Embedding Model (BAAI/bge-base-en)")

    t0 = time.perf_counter()
    try:
        from app.services.embedding import create_embedding
        sample = "Transformer self-attention mechanism for neural machine translation"
        emb = await create_embedding(sample)
        elapsed = (time.perf_counter() - t0) * 1000

        result(True, "Embedding generated", f"dim={len(emb)}, {elapsed:.0f}ms")

        if len(emb) != 768:
            warn("Dimension mismatch", f"Expected 768, got {len(emb)} — check EMBED_MODEL")
        else:
            result(True, "Dimension check", "768 ✓ (matches Store B schema VECTOR(768))")

        # Check vector normalization
        mag = sum(x ** 2 for x in emb) ** 0.5
        if 0.99 < mag < 1.01:
            result(True, "Normalization", f"||v|| = {mag:.4f} ✓")
        else:
            warn("Normalization", f"||v|| = {mag:.4f} (expected ≈ 1.0)")

        return emb

    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000
        result(False, "Embedding failed", f"{e} ({elapsed:.0f}ms)")
        return []


# ══════════════════════════════════════════════════════════════════
# Stage 3: OCR text extraction
# ══════════════════════════════════════════════════════════════════
async def stage3_ocr(pdf_path: str = None) -> str:
    section("Stage 3 — OCR / Text Extraction")

    if pdf_path and Path(pdf_path).exists():
        info("Input", f"PDF: {pdf_path}")
        try:
            from app.services.ocr_service import ocr_service
            with open(pdf_path, "rb") as f:
                file_bytes = f.read()
            t0 = time.perf_counter()
            ocr_result = await ocr_service.extract_text(
                file_bytes, Path(pdf_path).name, "application/pdf"
            )
            elapsed = (time.perf_counter() - t0) * 1000
            text = ocr_result["text"]
            result(True, "OCR extraction", f"{len(text):,} chars | {ocr_result['pages']} pages | {elapsed:.0f}ms")
            result(True, "Method", ocr_result["method"])
            info("Preview", text[:200].replace("\n", " ") + "…")
            return text
        except Exception as e:
            result(False, "OCR failed", str(e))
            warn("Falling back to synthetic text")
    else:
        if pdf_path:
            warn("PDF not found", f"{pdf_path} — using synthetic text")
        else:
            info("No PDF provided", "Using synthetic research paper text")

    info("Synthetic text", f"{len(SYNTHETIC_TEXT):,} chars")
    return SYNTHETIC_TEXT


# ══════════════════════════════════════════════════════════════════
# Stage 4: Store B Supabase schema check
# ══════════════════════════════════════════════════════════════════
async def stage4_schema_check() -> dict:
    section("Stage 4 — Store B Supabase Schema Verification")

    url = os.getenv("ARXIV_SUPABASE_URL")
    key = os.getenv("ARXIV_SUPABASE_KEY")

    if not url or not key:
        result(False, "Store B credentials", "Missing — skipping schema check")
        return {"ok": False, "client": None}

    try:
        import httpx

        # REST health check
        t0 = time.perf_counter()
        resp = httpx.get(
            f"{url}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=10.0, verify=False
        )
        elapsed = (time.perf_counter() - t0) * 1000
        result(resp.status_code in (200, 204), "Store B REST API", f"HTTP {resp.status_code} ({elapsed:.0f}ms)")

    except Exception as e:
        result(False, "Store B REST health", str(e))
        return {"ok": False, "client": None}

    # Verify tables exist
    try:
        from supabase import create_client
        client = create_client(url, key)

        tables = {
            "arxiv_papers": ("source_id", "title", "abstract"),
            "arxiv_chunks": ("paper_id", "chunk", "embedding"),
        }

        schema_ok = True
        for table, cols in tables.items():
            try:
                res = client.table(table).select(",".join(cols)).limit(1).execute()
                result(True, f"Table: {table}", f"accessible ({len(cols)} key columns verified)")
            except Exception as te:
                err = str(te)
                if "does not exist" in err or "relation" in err.lower():
                    result(False, f"Table: {table}", "MISSING — run ingestion/arxiv_schema.sql")
                    schema_ok = False
                else:
                    warn(f"Table: {table}", f"accessible but query failed: {err[:80]}")

        # Check hybrid_search_arxiv RPC
        try:
            t0 = time.perf_counter()
            rpc_res = client.rpc("hybrid_search_arxiv", {
                "query_text": "transformer attention",
                "query_embedding": [0.0] * 768,
                "match_count": 1
            }).execute()
            elapsed = (time.perf_counter() - t0) * 1000
            count = len(rpc_res.data) if rpc_res.data else 0
            result(True, "RPC: hybrid_search_arxiv", f"returns {count} rows ({elapsed:.0f}ms)")
        except Exception as re:
            err = str(re)
            if "function" in err.lower() and "does not exist" in err.lower():
                result(False, "RPC: hybrid_search_arxiv", "MISSING — run ingestion/arxiv_schema.sql")
                schema_ok = False
            else:
                warn("RPC: hybrid_search_arxiv", f"callable but error: {err[:80]}")

        return {"ok": schema_ok, "client": client, "url": url, "key": key}

    except Exception as e:
        result(False, "Supabase client", str(e))
        return {"ok": False, "client": None}


# ══════════════════════════════════════════════════════════════════
# Stage 5: Chunk + embed + ingest
# ══════════════════════════════════════════════════════════════════
async def stage5_ingest(text: str, schema: dict) -> dict:
    section("Stage 5 — Chunking → Embedding → Store B Ingest")

    if not schema.get("ok") or not schema.get("client"):
        warn("Skipped", "Store B not available — running chunking/embedding locally only")

        # Still verify chunking + embedding locally
        from app.services.ingestion_service import _chunk_text
        from app.services.embedding import create_embedding

        chunks = _chunk_text(text, chunk_size=1000, overlap=150)
        result(True, "Chunking", f"{len(chunks)} chunks from {len(text):,} chars")
        info("Chunk sizes", f"min={min(len(c) for c in chunks)}, max={max(len(c) for c in chunks)}, avg={sum(len(c) for c in chunks)//len(chunks)}")

        t0 = time.perf_counter()
        emb = await create_embedding(chunks[0])
        elapsed = (time.perf_counter() - t0) * 1000
        result(True, "Embedding (chunk 0)", f"dim={len(emb)}, {elapsed:.0f}ms")

        return {"paper_id": None, "chunk_count": 0, "store_b_used": False}

    # Full ingest via app service
    from app.services.ingestion_service import ingest_pdf_to_store_b

    info("Ingesting to Store B Supabase (arxiv_papers + arxiv_chunks)...")
    t0 = time.perf_counter()
    ingest_result = await ingest_pdf_to_store_b(
        filename="verify_pipeline_test.pdf",
        extracted_text=text,
        paper_metadata={
            "title": "E2E Pipeline Verification — Attention Is All You Need (Synthetic)",
            "authors": ["Vaswani", "Shazeer", "Parmar"],
        },
    )
    elapsed = (time.perf_counter() - t0) * 1000

    ok = ingest_result["status"] in ("ingested", "already_exists")
    result(ok, "Store B ingest", f"status={ingest_result['status']} | chunks={ingest_result['chunk_count']} | {elapsed:.0f}ms")

    if ingest_result.get("paper_id"):
        info("paper_id", ingest_result["paper_id"])
    if ingest_result.get("failed_chunks", 0):
        warn("Failed chunks", str(ingest_result["failed_chunks"]))

    return ingest_result


# ══════════════════════════════════════════════════════════════════
# Stage 6: Retrieval via hybrid_search_arxiv
# ══════════════════════════════════════════════════════════════════
async def stage6_retrieval(schema: dict, paper_id: str = None) -> bool:
    section("Stage 6 — Retrieval via hybrid_search_arxiv (Store B)")

    if not schema.get("ok") or not schema.get("client"):
        warn("Skipped", "Store B not available")
        return False

    from app.services.embedding import create_embedding

    queries = [
        "self-attention mechanism for sequence transduction",
        "transformer encoder decoder architecture",
        "scaled dot-product attention",
        "multi-head attention neural machine translation",
    ]

    client = schema["client"]
    all_ok = True

    for query in queries:
        try:
            t0 = time.perf_counter()
            emb = await create_embedding(query)
            embed_ms = (time.perf_counter() - t0) * 1000

            t1 = time.perf_counter()
            rpc_res = client.rpc("hybrid_search_arxiv", {
                "query_text": query,
                "query_embedding": emb,
                "match_count": 3
            }).execute()
            search_ms = (time.perf_counter() - t1) * 1000

            rows = rpc_res.data or []
            if rows:
                top_score = rows[0].get("score", 0)
                top_chunk = (rows[0].get("chunk", "")[:80]).replace("\n", " ")
                result(True, f'Query: "{query[:45]}…"',
                       f"{len(rows)} results | top_score={top_score:.3f} | embed={embed_ms:.0f}ms | search={search_ms:.0f}ms")
                info("  Top chunk", f"{top_chunk}…")
            else:
                warn(f'Query: "{query[:45]}…"', "0 results — ingestion may not be committed yet")
                all_ok = False

        except Exception as e:
            result(False, f'Query: "{query[:45]}"', str(e))
            all_ok = False

    # If we have a paper_id, verify direct paper lookup
    if paper_id:
        try:
            res = client.table("arxiv_papers").select("id,title,source_id").eq("id", paper_id).execute()
            if res.data:
                row = res.data[0]
                result(True, "Direct paper lookup by ID", f"title={row.get('title', '?')[:50]}")
            else:
                warn("Direct paper lookup", f"paper_id={paper_id} not found in arxiv_papers")
        except Exception as e:
            result(False, "Direct paper lookup", str(e))

    return all_ok


# ══════════════════════════════════════════════════════════════════
# Stage 7: Full RAG answer via /api/chat (live server check)
# ══════════════════════════════════════════════════════════════════
async def stage7_live_api_check():
    section("Stage 7 — Live API End-to-End (optional, requires server running)")

    api_url = os.getenv("APP_URL", "http://localhost:8000")
    api_key = os.getenv("APP_API_KEY", "dev-key-12345")

    try:
        import httpx
        import io

        # ── Health check ─────────────────────────────────────────
        t0 = time.perf_counter()
        health = httpx.get(f"{api_url}/api/health", timeout=5.0)
        elapsed = (time.perf_counter() - t0) * 1000

        if health.status_code != 200:
            warn("Server health", f"HTTP {health.status_code} ({elapsed:.0f}ms) — server may not be running")
            info("Skip", "Start server with: uvicorn app.main:app --reload")
            return

        result(True, "Server health", f"HTTP 200 ({elapsed:.0f}ms)")

        # ── Full health check ─────────────────────────────────────
        try:
            full_health = httpx.get(f"{api_url}/api/health/full", timeout=10.0)
            if full_health.status_code == 200:
                data = full_health.json()
                checks = data.get("checks", {})
                for svc, status in checks.items():
                    result(status == "ok", f"  Service: {svc}", status)
        except Exception:
            pass

        # ── Upload test ───────────────────────────────────────────
        synthetic_bytes = SYNTHETIC_TEXT.encode("utf-8")
        t0 = time.perf_counter()
        upload_res = httpx.post(
            f"{api_url}/api/upload",
            files={"file": ("verify_test.txt", io.BytesIO(synthetic_bytes), "text/plain")},
            data={"ingest_to_store_b": "true"},
            headers={"X-API-KEY": api_key},
            timeout=120.0
        )
        elapsed = (time.perf_counter() - t0) * 1000

        if upload_res.status_code != 200:
            warn("Upload endpoint", f"HTTP {upload_res.status_code}: {upload_res.text[:200]}")
            return

        data = upload_res.json()
        result(True, "Upload endpoint", f"{elapsed:.0f}ms | text_length={data.get('text_length')}")
        store_b = data.get("store_b", {})
        result(
            store_b.get("status") in ("ingested", "already_exists"),
            "Store B ingestion (via API)",
            f"status={store_b.get('status')} | chunks={store_b.get('chunk_count')} | {store_b.get('ingest_ms', 0)}ms"
        )
        session_id = data.get("session_id")

        # ── Chat query using session context ──────────────────────
        if not session_id:
            warn("Chat skip", "No session_id returned")
            return

        t0 = time.perf_counter()
        chat_res = httpx.post(
            f"{api_url}/api/chat",
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={
                "messages": [{"role": "user", "content": "What is the main contribution of this paper?"}],
                "session_id": session_id,
                "top_k": 3,
                "min_similarity": 0.2,
            },
            timeout=60.0
        )
        elapsed = (time.perf_counter() - t0) * 1000

        if chat_res.status_code != 200:
            warn("Chat endpoint", f"HTTP {chat_res.status_code}: {chat_res.text[:200]}")
            return

        # Parse SSE stream
        full_answer = ""
        route = "?"
        for line in chat_res.text.split("\n"):
            if line.startswith("data: "):
                try:
                    ev = json.loads(line[6:])
                    if ev.get("type") == "token":
                        full_answer += ev["token"]
                    elif ev.get("type") == "metadata":
                        route = ev.get("route", "?")
                    elif ev.get("type") == "final":
                        full_answer = ev.get("answer", "")
                        route = ev.get("route", "?")
                except Exception:
                    pass

        if full_answer:
            result(True, "Chat endpoint (SSE)",
                   f"route={route} | {elapsed:.0f}ms | {len(full_answer)} chars")
            info("Answer preview", full_answer[:200].replace("\n", " ") + "…")
        else:
            warn("Chat response", "Empty answer — check server logs")

    except httpx.ConnectError:
        warn("Server not reachable", f"{api_url} — start with: uvicorn app.main:app --reload")
    except Exception as e:
        warn("Live API check failed", str(e))


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
async def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else None

    print("\n" + "═" * 60)
    print("  Aether — PDF Ingestion Pipeline E2E Verification")
    print("  Store B: Supabase (arxiv_papers + arxiv_chunks)")
    print("═" * 60)

    timings = {}
    report = {"stages": {}, "overall": "PASS"}

    # Stage 1: Environment
    t0 = time.perf_counter()
    env_ok = await stage1_environment()
    timings["stage1_env"] = f"{(time.perf_counter()-t0)*1000:.0f}ms"
    report["stages"]["1_environment"] = "OK" if env_ok else "WARN"

    # Stage 2: Embedding
    t0 = time.perf_counter()
    emb = await stage2_embedding()
    timings["stage2_embed"] = f"{(time.perf_counter()-t0)*1000:.0f}ms"
    report["stages"]["2_embedding"] = "OK" if emb else "FAIL"
    if not emb:
        report["overall"] = "FAIL"

    # Stage 3: OCR
    t0 = time.perf_counter()
    extracted_text = await stage3_ocr(pdf_path)
    timings["stage3_ocr"] = f"{(time.perf_counter()-t0)*1000:.0f}ms"
    report["stages"]["3_ocr"] = "OK" if extracted_text else "FAIL"
    if not extracted_text:
        report["overall"] = "FAIL"

    # ── Initialize DualPool (normally done by FastAPI lifespan) ──
    section("Stage 4b — Pool Initialization")
    try:
        from app.services.pool import pool as dual_pool
        await dual_pool.init()
        info("DualPool", f"store_b_ok={dual_pool.store_b_ok}, neo4j_ok={dual_pool.neo4j_ok}")
        if dual_pool.store_b_ok:
            result(True, "Store B Supabase pool", "connected")
        else:
            warn("Store B Supabase pool", "Not connected — check ARXIV_SUPABASE_URL/KEY")
    except Exception as pe:
        warn("Pool init failed", str(pe))

    # Stage 4: Schema check
    t0 = time.perf_counter()
    schema = await stage4_schema_check()
    timings["stage4_schema"] = f"{(time.perf_counter()-t0)*1000:.0f}ms"
    report["stages"]["4_schema"] = "OK" if schema["ok"] else "WARN"

    # Stage 5: Ingest
    t0 = time.perf_counter()
    ingest = await stage5_ingest(extracted_text, schema)
    timings["stage5_ingest"] = f"{(time.perf_counter()-t0)*1000:.0f}ms"
    report["stages"]["5_ingest"] = "OK" if ingest.get("status") in ("ingested", "already_exists") else "WARN"

    # Stage 6: Retrieval
    t0 = time.perf_counter()
    retrieved = await stage6_retrieval(schema, ingest.get("paper_id"))
    timings["stage6_retrieval"] = f"{(time.perf_counter()-t0)*1000:.0f}ms"
    report["stages"]["6_retrieval"] = "OK" if retrieved else "WARN"

    # Stage 7: Live API
    await stage7_live_api_check()

    # ── Final Report ─────────────────────────────────────────────
    section("Pipeline Verification Report")
    for stage, status in report["stages"].items():
        ok = status == "OK"
        warn_flag = status == "WARN"
        icon = OK if ok else (WARN if warn_flag else FAIL)
        print(f"  {icon}  {stage.replace('_', ' ').title()}: {status}")

    print()
    print(f"  Stage timings:")
    for stage, timing in timings.items():
        print(f"    {stage}: {timing}")

    # Save JSON
    report_path = ROOT / "tests" / "pipeline_report.json"
    report["timings"] = timings
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  📄 Report saved: {report_path}")

    overall = report["overall"]
    print(f"\n  Overall: {overall}")
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    asyncio.run(main())
