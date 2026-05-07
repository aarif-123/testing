import asyncio
from typing import List, Dict, Optional
from ..core.logging_config import log
from ..core.exceptions import VectorStoreError
from ..utils.ranking import reciprocal_rank_fusion
from .pool import pool, get_supabase_client

async def vector_search(
    embedding: List[float],
    min_similarity: float,
    match_count: int,
    filter_ids: Optional[List[str]] = None,
    query_text: str = "machine learning" # Added for keyword fallback
) -> List[Dict]:
    """Search for relevant chunks across multiple vector stores with graceful degradation."""
    if not pool.supabase:
        log.error("Primary vector store (Store A) not connected")
        return []
    
    async def _run_search(async_client, rpc_name, params, label):
        try:
            # Use native async execution
            res = await async_client.rpc(rpc_name, params).execute()
            if hasattr(res, 'data') and res.data:
                return res.data
            return []
        except Exception as e:
            err_msg = str(e)
            log.warning(f"Vector search failed ({label}): {err_msg}")
            
            # Fallback to keyword search for Store A if vector search fails/times out
            if label == "Store A Chunks":
                try:
                    q = query_text
                    log.info(f"Attempting keyword fallback for Store A: {q}")
                    # Use native async text_search
                    kw_res = await async_client.table("papers") \
                        .select("*") \
                        .text_search("title", q) \
                        .execute()
                    # Apply limit manually if needed, or use a safer approach
                    data = kw_res.data[:params.get("match_count", 10)] if kw_res.data else []
                    if data:
                        log.info(f"Keyword fallback found {len(data)} results for Store A")
                        # Format to match RPC return structure (needs chunk and score/similarity)
                        formatted_data = []
                        for r in data:
                            formatted_data.append({
                                "id": r.get("id"),
                                "paper_id": r.get("id"),
                                "title": r.get("title"),
                                "chunk": r.get("abstract", "No abstract available."),
                                "similarity": 0.5 # Mock similarity for keyword matches
                            })
                        return formatted_data
                except Exception as kw_e:
                    log.error(f"Keyword fallback failed for Store A: {kw_e}")
            return []

    # Store A Payload (Old schema uses match_paper_chunks)
    payload_a = {
        "query_embedding": embedding,
        "match_threshold": min_similarity,
        "match_count": match_count,
        "filter_ids": filter_ids or []
    }

    tasks = [
        _run_search(pool.async_supabase, "match_paper_chunks", payload_a, "Store A Chunks")
    ]
    
    # Store B (ArXiv Hybrid Search)
    if pool.store_b_ok:
        payload_b = {
            "query_text": query_text, 
            "query_embedding": embedding,
            "match_count": match_count
        }
        # Note: If hybrid_search_arxiv fails due to schema mismatch, it will be caught by _run_search
        tasks.append(
            _run_search(pool.arxiv_async_supabase, "hybrid_search_arxiv", payload_b, "Store B Hybrid")
        )

    results = await asyncio.gather(*tasks)
    
    # Flatten, merge, and filter out 'Synthetic' mocked data
    all_chunks = []
    valid_results = []
    
    for res_list in results:
        if res_list:
            # Strictly filter out any mock/synthetic data uploaded previously
            filtered_list = [
                c for c in res_list 
                if not (c.get("title") and "(Synthetic)" in c["title"])
            ]
            if filtered_list:
                valid_results.append(filtered_list)
    
    if not valid_results:
        return []
        
    if len(valid_results) > 1:
        # Use RRF to combine different store results
        return reciprocal_rank_fusion(valid_results)
    
    return valid_results[0]

async def hybrid_keyword_search(query_text: str, top_k: int) -> List[Dict]:
    """Perform keyword-focused search for specific entities or topics."""
    if not pool.store_b_ok:
        return []
        
    payload = {
        "query_text": query_text,
        "query_embedding": [0.0] * 768, 
        "match_count": top_k
    }
    
    try:
        res = await pool.arxiv_async_supabase.rpc("hybrid_search_arxiv", payload).execute()
        return res.data if res.data else []
    except Exception as e:
        log.warning(f"Keyword search failed in Store B: {e}")
        return []
