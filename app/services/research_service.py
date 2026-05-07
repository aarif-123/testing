import time
import asyncio
from typing import List, Dict
from fastapi import HTTPException

from ..core.config import settings
from ..core.logging_config import log
from ..core.models import QueryPlan, ConversationRequest
from ..core.exceptions import EmbeddingError, LLMError
from .vector_service import vector_search
from .embedding import create_embedding


class ResearchService:
    """The 'Brain Pipeline' Orchestrator suggested by senior mentor."""

    async def execute_plan(
        self, plan: QueryPlan, req: ConversationRequest, rid: str, t0: float, plan_ms: int = 0
    ) -> Dict:
        # 0. Global Response Cache Check
        from ..utils import cache
        ck = cache.cache_key("response", plan.cache_key_str, req.model_dump_json())
        cached_res = await cache.get_cache("response", ck)
        if cached_res:
            log.info(f"[{rid}] Global Response CACHE HIT")
            cached_res["request_id"] = rid # Update RID for tracking
            cached_res["latency_ms"] = int((time.time() - t0) * 1000)
            cached_res["cached"] = True
            return cached_res

        query = plan.standalone_query
        graph_nodes: List[Dict] = []
        warning = None
        # Enhanced latency tracking
        latency_metrics = {
            "plan_ms": plan_ms,
            "mcp_ms": 0,
            "embed_ms": 0,
            "vector_ms": 0,
            "graph_ms": 0,
            "llm_ms": 0,
            "total_ms": 0
        }

        # 1. Specialized Route: chitchat (Fast Bypass)
        if plan.route == "chitchat":
            from .llm import groq_chat
            log.info(f"[{rid}] Routing to CHITCHAT (Bypass)")
            msgs = [{"role": "system", "content": (
                "You are Aether, a helpful GraphRAG Research Assistant. "
                "Answer this general query briefly and professionally. "
                "If the user asks what you can do, explain you are a research assistant."
            )}] + [
                {"role": m.role, "content": m.content} for m in req.messages
            ]
            try:
                llm_t0 = time.time()
                answer = await groq_chat(msgs, settings.REASON_MODEL, temperature=0.7)
                latency_metrics["llm_ms"] = int((time.time() - llm_t0) * 1000)
                return {
                    "request_id": rid,
                    "answer": answer,
                    "route": "chitchat",
                    "latency_ms": int((time.time() - t0) * 1000),
                    "latency_metrics": latency_metrics,
                    "model_used": settings.REASON_MODEL
                }
            except Exception as e:
                log.error(f"Chitchat failed: {e}")

        # 2. Specialized Route: trending (Fast Analytics)
        if plan.route == "trending":
            from .graph_service import get_trending_papers
            log.info(f"[{rid}] Routing to TRENDING")
            g_t0 = time.time()
            trending = await get_trending_papers(limit=5)
            latency_metrics["graph_ms"] = int((time.time() - g_t0) * 1000)
            if trending:
                answer = "Here are some trending papers in the database:\n\n"
                for p in trending:
                    answer += f"- **{p['title']}** ({p['year']}) - {p.get('citations', 0)} citations\n"
                return {
                    "request_id": rid,
                    "answer": answer,
                    "route": "trending",
                    "papers": trending,
                    "latency_ms": int((time.time() - t0) * 1000),
                    "latency_metrics": latency_metrics
                }

        # 3. Specialized Route: entity_lookup (Factual Graph Query)
        if plan.route == "entity_lookup":
            from .graph_service import retrieve_graph_papers
            log.info(f"[{rid}] Routing to ENTITY_LOOKUP")
            g_t0 = time.time()
            anchors = plan.graph_anchors or [query]
            papers = await retrieve_graph_papers(keywords=anchors, anchors=anchors, limit=3)
            latency_metrics["graph_ms"] = int((time.time() - g_t0) * 1000)
            if not papers:
                return {
                    "request_id": rid,
                    "answer": "⚠️ No matching paper found.",
                    "route": "entity_lookup",
                    "latency_metrics": latency_metrics
                }
            p = papers[0]
            answer = f"**{p.get('title','?')}** ({p.get('year','?')})\n\nAuthors: {', '.join(p.get('authors', []))}"
            return {
                "request_id": rid,
                "answer": answer,
                "route": "entity_lookup",
                "papers": papers,
                "latency_metrics": latency_metrics
            }

        # 3b. Specialized Route: compare (Side-by-side paper comparison)
        if plan.route == "compare":
            from .graph_service import retrieve_graph_papers
            from ..utils.prompts import compare_prompt
            from .llm import groq_chat
            log.info(f"[{rid}] Routing to COMPARE")
            anchors = plan.graph_anchors or []
            g_t0 = time.time()
            if len(anchors) >= 2:
                # Fetch both papers in parallel
                results = await asyncio.gather(
                    retrieve_graph_papers(keywords=[anchors[0]], anchors=[anchors[0]], limit=2),
                    retrieve_graph_papers(keywords=[anchors[1]], anchors=[anchors[1]], limit=2),
                    return_exceptions=True
                )
                papers_a = results[0] if not isinstance(results[0], Exception) else []
                papers_b = results[1] if not isinstance(results[1], Exception) else []
                all_papers = papers_a + papers_b
            else:
                # Single anchor or none — fall back to keyword search
                all_papers = await retrieve_graph_papers(
                    keywords=anchors or plan.vector_keywords or [query],
                    anchors=anchors,
                    limit=6
                )
            latency_metrics["graph_ms"] = int((time.time() - g_t0) * 1000)

            # Get vector chunks for context
            try:
                embedding = await create_embedding(query)
                chunks = await vector_search(embedding=embedding, match_count=4, query_text=query)
            except Exception:
                chunks = []

            prompt = compare_prompt(query, chunks, all_papers)
            model = settings.HEAVY_MODEL if req.use_heavy else settings.REASON_MODEL
            msgs = [{"role": "system", "content": prompt}] + [
                {"role": m.role, "content": m.content} for m in req.messages
            ]
            try:
                llm_t0 = time.time()
                answer = await groq_chat(msgs, model, temperature=0.0, max_tokens=1800)
                latency_metrics["llm_ms"] = int((time.time() - llm_t0) * 1000)
            except LLMError as e:
                raise HTTPException(502, f"Compare generation failed: {e}")

            total_latency = int((time.time() - t0) * 1000)
            latency_metrics["total_ms"] = total_latency
            return {
                "request_id": rid,
                "answer": answer,
                "route": "compare",
                "source_nodes": {
                    "papers": [
                        {"id": p.get("research_id"), "title": p.get("title"),
                         "authors": p.get("authors", []), "year": p.get("year")}
                        for p in all_papers
                    ],
                    "evidence_chunks": []
                },
                "latency_ms": total_latency,
                "latency_metrics": latency_metrics,
                "model_used": model,
            }

        # 4. Optimized Parallel Retrieval (ArXiv MCP, Vector, Context)
        mcp_run = False

        async def fetch_mcp_data():
            try:
                from .arxiv_mcp import arxiv_mcp
                from .ingestion_service import ingest_paper_to_store_b
                mcp_t0 = time.time()
                keywords = plan.vector_keywords or [kw.strip() for kw in query.split() if len(kw) > 3]
                base_query = " ".join(keywords[:5])
                search_query = base_query

                if plan.domain and plan.domain.lower() != "unknown":
                    if "." in plan.domain:
                        search_query = f"cat:{plan.domain} AND ({base_query})"
                    elif " " in plan.domain:
                        search_query = f'all:"{plan.domain}" AND ({base_query})'
                    else:
                        search_query = f"all:{plan.domain} AND ({base_query})"

                mcp_res = await arxiv_mcp.search_papers(search_query, limit=12)
                latency_metrics["mcp_ms"] += int((time.time() - mcp_t0) * 1000)

                if not mcp_res:
                    log.info(f"[{rid}] Zero ArXiv results with domain filter, retrying broad...")
                    mcp_res = await arxiv_mcp.search_papers(base_query, limit=12)

                s = []
                logs = []
                tasks = []
                temp_papers = []
                for raw in mcp_res:
                    temp_papers.extend(arxiv_mcp.parse_multiple_papers(raw))

                for i, p_temp in enumerate(temp_papers[:5]):
                    if p_temp.get("source_id"):
                        tasks.append(arxiv_mcp.get_details(p_temp["source_id"]))

                if tasks:
                    log.info(f"[{rid}] Enriched analysis: fetching details for {len(tasks)} papers...")
                    enriched_results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, res in enumerate(enriched_results):
                        if not isinstance(res, Exception) and res:
                            res_txt = ""
                            if hasattr(res, 'content') and isinstance(res.content, list) and res.content:
                                res_txt = res.content[0].text if hasattr(res.content[0], 'text') else str(res.content[0])
                            else:
                                res_txt = str(res)
                            parsed_detail = arxiv_mcp.format_for_db(res_txt)
                            if parsed_detail.get("abstract"):
                                temp_papers[i]["abstract"] = parsed_detail["abstract"]

                ingest_tasks = [ingest_paper_to_store_b(p) for p in temp_papers]
                for t in ingest_tasks:
                    asyncio.create_task(t)
                return temp_papers, logs
            except Exception as e:
                log.error(f"MCP failed: {e}")
                return [], []

        async def fetch_vector_data():
            try:
                log.debug(f"[{rid}] Generating embedding...")
                e_t0 = time.time()
                embedding = await create_embedding(
                    " ".join(plan.vector_keywords or plan.graph_anchors or [query])
                )
                latency_metrics["embed_ms"] = int((time.time() - e_t0) * 1000)
                
                log.debug(f"[{rid}] Running vector search...")
                v_t0 = time.time()
                res = await vector_search(
                    embedding=embedding,
                    min_similarity=req.min_similarity,
                    match_count=req.top_k,
                    query_text=query
                )
                latency_metrics["vector_ms"] = int((time.time() - v_t0) * 1000)
                return res
            except EmbeddingError as e:
                log.error(f"Vector pipeline failed: {e}")
                return []

        async def fetch_user_context():
            try:
                log.debug(f"[{rid}] Fetching user context graph...")
                from .user_graph import user_graph
                g_t0 = time.time()
                context = await user_graph.get_user_context(user_id="u_aether_01", limit=3)
                latency_metrics["graph_ms"] += int((time.time() - g_t0) * 1000)
                if context:
                    context_strings = [f"{c['topic']} (interest: {c['weight']})" for c in context]
                    return "USER CONTEXT: The user is currently interested in: " + ", ".join(context_strings)
                return ""
            except Exception as e:
                log.error(f"User Context fetch failed: {e}")
                return ""

        async def fetch_session_context():
            if not req.session_id:
                return "", []
            try:
                from .session_service import session_service
                log.debug(f"[{rid}] Fetching session context for {req.session_id}...")
                ctx = await session_service.get_session_context(req.session_id)
                papers = await session_service.get_session_papers(req.session_id)
                return ctx, papers
            except Exception as e:
                log.error(f"Session Context fetch failed: {e}")
                return "", []

        async def fetch_graph_data():
            try:
                from .graph_service import retrieve_graph_papers
                log.debug(f"[{rid}] Running Knowledge Graph lookup...")
                g_t0 = time.time()
                anchors = plan.graph_anchors or plan.vector_keywords or [query]
                res = await retrieve_graph_papers(keywords=anchors, anchors=anchors, limit=5)
                latency_metrics["graph_ms"] += int((time.time() - g_t0) * 1000)
                return res
            except Exception as e:
                log.error(f"Knowledge Graph search failed: {e}")
                return []

        # Determine which tasks to run concurrently
        tasks_to_run = [fetch_vector_data(), fetch_user_context(), fetch_graph_data(), fetch_session_context()]
        mcp_future_idx = -1
        
        # If we have a session ID, restrict to PDF context for grounding
        pdf_only_mode = bool(req.session_id)

        if plan.route not in ("chitchat", "trending", "entity_lookup") \
           and not pdf_only_mode:
            mcp_run = True
            tasks_to_run.append(fetch_mcp_data())
            mcp_future_idx = 4
            
        try:
            results = await asyncio.gather(*tasks_to_run)
            session_context_str, session_papers_list = results[3]
            chunks = results[0]
            user_context_str = results[1]
            graph_retrieved = results[2]
            
            # --- STRATEGIC COMBINATION: Cross-Pollination ---
            # 1. If we found graph papers but no vector chunks, fetch chunks for those papers
            if graph_retrieved and not chunks:
                log.info(f"[{rid}] Strategic: Found graph nodes, fetching vector chunks for them...")
                graph_ids = [p["research_id"] for p in graph_retrieved if p.get("research_id")]
                if graph_ids:
                    from .vector_service import get_chunks_by_ids
                    extra_chunks = await get_chunks_by_ids(graph_ids[:5])
                    chunks.extend(extra_chunks)

            # 2. If we found vector chunks but no graph nodes, expand from those chunks
            if chunks and not graph_retrieved:
                log.info(f"[{rid}] Strategic: Found vector chunks, expanding graph neighborhood...")
                found_titles = list(set([c["title"] for c in chunks if c.get("title")]))
                if found_titles:
                    from .graph_service import retrieve_graph_papers
                    extra_graph = await retrieve_graph_papers(keywords=found_titles[:3], limit=5)
                    graph_retrieved.extend(extra_graph)

            # --- END STRATEGIC COMBINATION ---

            graph_nodes.extend(graph_retrieved)
            
            # Formally inject session papers into the retrieval results
            if session_papers_list:
                has_session_chunks = False
                for sp in session_papers_list:
                    sid = sp.get("session_id") or req.session_id
                    full_data = await cache.get_cache("session_papers", f"{sid}:{sp['id']}")
                    
                    paper_obj = {
                        "id": sp["id"],
                        "title": sp.get("filename", "Uploaded Document"),
                        "authors": ["User Upload"],
                        "year": sp.get("year", "2024"),
                        "url": None,
                        "abstract": "User-provided research document context."
                    }
                    if paper_obj not in graph_nodes:
                        graph_nodes.append(paper_obj)
                    
                    extracted_text = None
                    if full_data and full_data.get("extracted_text"):
                        extracted_text = full_data["extracted_text"]
                    
                    if extracted_text:
                        chunks.append({
                            "chunk": extracted_text[:100000],
                            "title": sp.get("filename"),
                            "score": 1.0,
                            "metadata": {"source": "upload"}
                        })
                        has_session_chunks = True
                
                if not has_session_chunks and session_context_str:
                    log.info(f"[{rid}] Individual paper cache miss, using session_context fallback")
                    chunks.append({
                        "chunk": session_context_str[:10000],
                        "title": session_papers_list[0].get("filename") if session_papers_list else "Session Document",
                        "score": 1.0,
                        "metadata": {"source": "upload_fallback"}
                    })
            
            if session_context_str and not chunks:
                user_context_str = f"SESSION DOCUMENT CONTEXT:\n{session_context_str}\n\n" + user_context_str
                
            if mcp_future_idx != -1:
                structured, mcp_logs = results[mcp_future_idx]
                if structured:
                    graph_nodes.extend(structured)
                    warning = "Research enriched with LIVE ArXiv data."
            
            if pdf_only_mode:
                warning = "Response generated STRICTLY from the uploaded document(s)."
        except Exception as e:
            log.warning(f"Parallel retrieval failed: {e}")
            chunks, user_context_str, session_papers_list = [], "", []

        structured = []  # ensure always defined for mcp_stats below
        if not chunks and not graph_nodes and not mcp_run and plan.route != "chitchat" and not pdf_only_mode:
            log.info(f"[{rid}] No local evidence. Triggering ArXiv Fallback...")
            mcp_run = True
            structured, mcp_logs = await fetch_mcp_data()
            if structured:
                graph_nodes.extend(structured)
                warning = "No local data found. Results from LIVE ArXiv research."
            else:
                warning = "No relevant evidence found."
        elif not chunks and not graph_nodes and not pdf_only_mode:
            warning = "No relevant evidence found in local stores."

        # Final Answer Synthesis (Optimized with heavy model selection)
        from .llm import groq_chat
        model = settings.HEAVY_MODEL if req.use_heavy else settings.REASON_MODEL
        final_query_context = f"{user_context_str}\n\nORIGINAL QUERY:\n{query}" if user_context_str else query
        from ..utils.prompts import grounded_prompt
        prompt = grounded_prompt(final_query_context, chunks, graph_nodes)
        msgs = [{"role": "system", "content": prompt}] + [{"role": m.role, "content": m.content} for m in req.messages]
        
        try:
            llm_t0 = time.time()
            log.debug(f"[{rid}] Synthesizing answer with {model}...")
            answer = await groq_chat(msgs, model, temperature=0.0, max_tokens=3500)
            latency_metrics["llm_ms"] = int((time.time() - llm_t0) * 1000)
        except LLMError as e:
            raise HTTPException(502, f"Generation failed: {e}")

        if plan.vector_keywords:
            from .user_graph import user_graph
            asyncio.create_task(user_graph.update_user_interests(
                user_id="u_aether_01", query_text=query, topics=plan.vector_keywords[:3]
            ))

        total_latency = int((time.time() - t0) * 1000)
        latency_metrics["total_ms"] = total_latency
        res = {
            "request_id": rid,
            "answer": answer,
            "route": plan.route,
            "plan": {"standalone_query": plan.standalone_query, "reasoning_path": plan.reasoning_path},
            "source_nodes": {
                "papers": [
                    {
                        "id": p.get("id") or p.get("research_id") or p.get("source_id"),
                        "title": p.get("title"),
                        "authors": p.get("authors") or [],
                        "year": p.get("year"),
                        "url": p.get("url"),
                        "abstract": p.get("abstract"),
                        "categories": p.get("categories") or [p.get("domain")] if p.get("domain") else []
                    } for p in graph_nodes
                ],
                "evidence_chunks": [
                    {"chunk": c.get("chunk"), "title": c.get("title"), "score": round(c.get("score" if "score" in c else "similarity") or 0, 3)} for c in chunks
                ]
            },
            "latency_ms": total_latency,
            "latency_metrics": latency_metrics,
            "model_used": model,
            "confidence_score": round(min(1.0, (len(chunks) * 0.15 + len(graph_nodes) * 0.1)), 2),
            "warning": warning,
            "session_id": req.session_id,
            "mcp_stats": {"used": mcp_run, "found": len(structured) if 'structured' in locals() and structured else 0}
        }
        await cache.set_cache("response", ck, res)
        return res

    async def execute_plan_stream(
        self, plan, req: ConversationRequest, rid: str, t0: float, plan_ms: int = 0
    ):
        """
        Streaming variant of execute_plan.

        Strategy:
        - All retrieval (vector, graph, user context, session, MCP) runs in parallel
          as normal — these are fast and don't benefit from streaming.
        - Only the final LLM synthesis is streamed token-by-token via SSE.
        - The first SSE event carries full metadata (papers, plan, latency so far)
          so the frontend can render source cards immediately.

        Yields SSE-formatted strings: "data: <json>\\n\\n"
        """
        import json as _json
        from .llm import groq_chat_stream
        from ..utils.prompts import grounded_prompt

        # Run full retrieval pipeline (re-use execute_plan logic up to LLM call)
        # We call the non-streaming execute_plan but intercept before LLM synthesis.
        # The cleanest way: run retrieval inline, identical to execute_plan.
        query = plan.standalone_query
        warning = None
        latency_metrics = {
            "plan_ms": plan_ms, "mcp_ms": 0, "embed_ms": 0,
            "vector_ms": 0, "graph_ms": 0, "llm_ms": 0, "total_ms": 0
        }

        # Fast routes: delegate to non-streaming execute_plan (they're instant)
        if plan.route in ("chitchat", "trending", "entity_lookup", "compare"):
            result = await self.execute_plan(plan, req, rid, t0, plan_ms=plan_ms)
            yield f"data: {_json.dumps({'type': 'final', **result})}\n\n"
            return

        # --- Parallel retrieval (identical to execute_plan) ---
        from .embedding import create_embedding
        from .vector_service import vector_search
        from .graph_service import retrieve_graph_papers
        from .arxiv_mcp import arxiv_mcp
        from .ingestion_service import ingest_paper_to_store_b
        from ..utils import cache
        graph_nodes = []
        chunks = []

        async def _fetch_vector():
            try:
                e_t0 = time.time()
                emb = await create_embedding(
                    " ".join(plan.vector_keywords or plan.graph_anchors or [query])
                )
                latency_metrics["embed_ms"] = int((time.time() - e_t0) * 1000)
                v_t0 = time.time()
                res = await vector_search(
                    embedding=emb,
                    min_similarity=req.min_similarity,
                    match_count=req.top_k,
                    query_text=query
                )
                latency_metrics["vector_ms"] = int((time.time() - v_t0) * 1000)
                return res
            except Exception as e:
                log.error(f"[stream] Vector failed: {e}")
                return []

        async def _fetch_graph():
            try:
                g_t0 = time.time()
                anchors = plan.graph_anchors or plan.vector_keywords or [query]
                res = await retrieve_graph_papers(keywords=anchors, anchors=anchors, limit=5)
                latency_metrics["graph_ms"] += int((time.time() - g_t0) * 1000)
                return res
            except Exception:
                return []

        async def _fetch_user_ctx():
            try:
                from .user_graph import user_graph
                ctx = await user_graph.get_user_context(user_id="u_aether_01", limit=3)
                if ctx:
                    return "USER CONTEXT: Interested in: " + ", ".join(
                        f"{c['topic']} (weight: {c['weight']})" for c in ctx
                    )
                return ""
            except Exception:
                return ""

        async def _fetch_session():
            if not req.session_id:
                return "", []
            try:
                from .session_service import session_service
                ctx = await session_service.get_session_context(req.session_id)
                papers = await session_service.get_session_papers(req.session_id)
                return ctx, papers
            except Exception:
                return "", []

        async def _fetch_mcp():
            try:
                m_t0 = time.time()
                keywords = plan.vector_keywords or [kw for kw in query.split() if len(kw) > 3]
                base_query = " ".join(keywords[:5])
                search_query = base_query

                if plan.domain and plan.domain.lower() != "unknown":
                    if "." in plan.domain:
                        search_query = f"cat:{plan.domain} AND ({base_query})"
                    elif " " in plan.domain:
                        search_query = f'all:"{plan.domain}" AND ({base_query})'
                    else:
                        search_query = f"all:{plan.domain} AND ({base_query})"

                # Fetch top 10 papers for richer researcher-grade responses
                mcp_res = await arxiv_mcp.search_papers(search_query, limit=10)
                latency_metrics["mcp_ms"] = int((time.time() - m_t0) * 1000)

                if not mcp_res:
                    log.info("[stream] Zero ArXiv results with domain filter, retrying broad...")
                    mcp_res = await arxiv_mcp.search_papers(base_query, limit=10)

                temp_papers = []
                for raw in mcp_res:
                    temp_papers.extend(arxiv_mcp.parse_multiple_papers(raw))

                tasks = []
                for i, p_temp in enumerate(temp_papers[:5]):
                    if p_temp.get("source_id"):
                        tasks.append(arxiv_mcp.get_details(p_temp["source_id"]))

                if tasks:
                    log.info(f"[{rid}] Enriched analysis: fetching full abstracts for {len(tasks)} papers...")
                    enriched_results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, res in enumerate(enriched_results):
                        if not isinstance(res, Exception) and res:
                            res_txt = str(res)
                            parsed_detail = arxiv_mcp.format_for_db(res_txt)
                            if parsed_detail.get("abstract"):
                                temp_papers[i]["abstract"] = parsed_detail["abstract"]

                async def background_mcp_ingest(paper):
                    # 1. Quickly ingest the metadata and abstract (baseline Store B)
                    from .ingestion_service import ingest_paper_to_store_b, ingest_pdf_to_store_b
                    await ingest_paper_to_store_b(paper)
                    
                    # 2. Deep Ingestion: Use the MCP 'read_paper' tool to get the FULL text
                    arxiv_id = paper.get("source_id")
                    if arxiv_id:
                        try:
                            log.info(f"[Deep Ingest] Fetching full text via MCP read_paper for {arxiv_id}...")
                            read_res = await arxiv_mcp.read_paper(arxiv_id)
                            
                            # Parse the MCP tool result safely
                            full_text = None
                            if isinstance(read_res, list) and len(read_res) > 0:
                                if hasattr(read_res[0], 'text'):
                                    full_text = read_res[0].text
                            elif hasattr(read_res, 'text'):
                                full_text = read_res.text
                            elif isinstance(read_res, str):
                                full_text = read_res
                                
                            if full_text and len(full_text) > 500:
                                log.info(f"[Deep Ingest] Uploading {len(full_text)} chars of full text to Store B for {arxiv_id}...")
                                # We pass the MCP's full markdown as if it were OCR'd text
                                await ingest_pdf_to_store_b(
                                    filename=f"arxiv_{arxiv_id}.md",
                                    extracted_text=full_text,
                                    paper_metadata=paper
                                )
                        except Exception as e:
                            log.error(f"[Deep Ingest] Failed to deep-ingest {arxiv_id}: {e}")

                # For an IN-DEPTH immediate response, wait for the first paper's full text
                first_paper_deep_text = None
                if temp_papers:
                    top_paper = temp_papers[0]
                    arxiv_id = top_paper.get("source_id")
                    if arxiv_id:
                        log.info(f"[stream] Fetching deep context synchronously for top paper: {arxiv_id}...")
                        read_res = await arxiv_mcp.read_paper(arxiv_id)
                        if hasattr(read_res, 'text'):
                            first_paper_deep_text = read_res.text
                        elif isinstance(read_res, list) and len(read_res) > 0 and hasattr(read_res[0], 'text'):
                            first_paper_deep_text = read_res[0].text
                        elif isinstance(read_res, str):
                            first_paper_deep_text = read_res

                # Fire off the deep ingestion for all papers in the background
                for p in temp_papers:
                    asyncio.create_task(background_mcp_ingest(p))
                
                return temp_papers, first_paper_deep_text
            except Exception as e:
                log.error(f"[stream] MCP failed: {e}")
                return [], None

        pdf_only = bool(req.session_id)
        tasks = [_fetch_vector(), _fetch_graph(), _fetch_user_ctx(), _fetch_session()]
        run_mcp = plan.route not in ("chitchat", "trending", "entity_lookup") and not pdf_only
        if run_mcp:
            tasks.append(_fetch_mcp())

        results = await asyncio.gather(*tasks, return_exceptions=True)
        chunks = results[0] if not isinstance(results[0], Exception) else []
        graph_nodes = list(results[1]) if not isinstance(results[1], Exception) else []
        user_ctx = results[2] if not isinstance(results[2], Exception) else ""
        session_ctx, session_papers = (results[3] if not isinstance(results[3], Exception) else ("", []))
        if run_mcp and len(results) > 4:
            mcp_res_tuple = results[4] if not isinstance(results[4], Exception) else ([], None)
            mcp_papers = mcp_res_tuple[0] if isinstance(mcp_res_tuple, tuple) else mcp_res_tuple
            first_paper_deep_text = mcp_res_tuple[1] if isinstance(mcp_res_tuple, tuple) and len(mcp_res_tuple) > 1 else None

            if mcp_papers:
                graph_nodes.extend(mcp_papers)
                warning = "Research enriched with LIVE ArXiv data."
                
            if first_paper_deep_text:
                chunks.append({
                    "chunk": first_paper_deep_text[:40000],  # 40k chars for deep researcher context
                    "title": mcp_papers[0].get("title", "ArXiv Source") if mcp_papers else "ArXiv Source",
                    "score": 1.0,
                    "metadata": {"source": "mcp_deep_read"}
                })

        # Session paper chunks injection
        if session_papers:
            for sp in session_papers:
                sid = sp.get("session_id") or req.session_id
                full_data = await cache.get_cache("session_papers", f"{sid}:{sp['id']}")
                if full_data and full_data.get("extracted_text"):
                    chunks.append({
                        "chunk": full_data["extracted_text"][:100000],
                        "title": sp.get("filename"),
                        "score": 1.0,
                        "metadata": {"source": "upload"}
                    })
        if pdf_only:
            warning = "Response generated STRICTLY from the uploaded document(s)."

        # Build prompt — cap chunks to avoid LLM context window timeouts
        capped_chunks = chunks[:12] if len(chunks) > 12 else chunks
        # Truncate very large chunks to 6000 chars each for richer evidence
        for c in capped_chunks:
            if c.get("chunk") and len(c["chunk"]) > 6000:
                c["chunk"] = c["chunk"][:6000] + "..."
        model = settings.HEAVY_MODEL if req.use_heavy else settings.REASON_MODEL
        final_query = f"{user_ctx}\n\nORIGINAL QUERY:\n{query}" if user_ctx else query
        prompt = grounded_prompt(final_query, capped_chunks, graph_nodes)
        msgs = [{"role": "system", "content": prompt}] + [
            {"role": m.role, "content": m.content} for m in req.messages
        ]

        # --- Send metadata event first ---
        retrieval_latency = int((time.time() - t0) * 1000)
        meta_event = {
            "type": "metadata",
            "request_id": rid,
            "route": plan.route,
            "plan": {
                "standalone_query": plan.standalone_query,
                "reasoning_path": plan.reasoning_path
            },
            "source_nodes": {
                "papers": [
                    {
                        "id": p.get("id") or p.get("research_id") or p.get("source_id"),
                        "title": p.get("title"),
                        "authors": p.get("authors") or [],
                        "year": p.get("year"),
                        "url": p.get("url"),
                        "abstract": p.get("abstract"),
                        "categories": p.get("categories") or [p.get("domain")] if p.get("domain") else []
                    } for p in graph_nodes
                ],
                "evidence_chunks": [
                    {
                        "chunk": c.get("chunk", ""),
                        "title": c.get("title"),
                        "score": round(c.get("score", 0), 3)
                    } for c in capped_chunks
                ]
            },
            "model_used": model,
            "retrieval_ms": retrieval_latency,
            "warning": warning,
            "session_id": req.session_id,
        }
        yield f"data: {_json.dumps(meta_event)}\n\n"

        # --- Stream LLM synthesis token by token ---
        llm_t0 = time.time()
        full_answer = []
        try:
            async for token in groq_chat_stream(msgs, model, temperature=0.0, max_tokens=4096):
                full_answer.append(token)
                yield f"data: {_json.dumps({'type': 'token', 'token': token})}\n\n"
        except LLMError as e:
            yield f"data: {_json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
            return

        latency_metrics["llm_ms"] = int((time.time() - llm_t0) * 1000)
        latency_metrics["total_ms"] = int((time.time() - t0) * 1000)

        answer = "".join(full_answer)

        # Update user interest graph in background
        if plan.vector_keywords:
            from .user_graph import user_graph
            asyncio.create_task(user_graph.update_user_interests(
                user_id="u_aether_01", query_text=query, topics=plan.vector_keywords[:3]
            ))

        # Send done event with final latency
        done_event = {
            "type": "done",
            "request_id": rid,
            "latency_ms": latency_metrics["total_ms"],
            "latency_metrics": latency_metrics,
            "confidence_score": round(min(1.0, (len(chunks) * 0.15 + len(graph_nodes) * 0.1)), 2),
        }
        yield f"data: {_json.dumps(done_event)}\n\n"

        # Cache the full response for future identical queries
        cached_res = {
            "request_id": rid,
            "answer": answer,
            "route": plan.route,
            **meta_event,
            "latency_ms": latency_metrics["total_ms"],
            "latency_metrics": latency_metrics,
        }
        await cache.set_cache("response", cache.cache_key("response", plan.cache_key_str, req.model_dump_json()), cached_res)


research_service = ResearchService()
