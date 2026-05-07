import numpy as np
from typing import List, Dict, Optional
from ..core.config import settings

SIMILARITY_KEYS = ("similarity", "score", "relevance", "_score", "sim")

def get_chunk_similarity(chunk: Dict) -> float:
    """Extract similarity score from a chunk dictionary using common keys."""
    for key in SIMILARITY_KEYS:
        if key in chunk:
            try:
                return float(chunk[key])
            except (TypeError, ValueError):
                pass
    return 1.0

def reciprocal_rank_fusion(
    result_lists: List[List[Dict]], k: int = 60
) -> List[Dict]:
    """Merge multiple ranked result lists using RRF."""
    scores: Dict[str, float] = {}
    chunks: Dict[str, Dict] = {}
    for lst in result_lists:
        for rank, chunk in enumerate(lst):
            # Generate unique ID for the chunk
            cid = str(
                chunk.get("id")
                or f"{chunk.get('research_id','')}_{chunk.get('chunk_number','')}"
            )
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            chunks[cid] = chunk
    
    return [
        chunks[cid] for cid in sorted(scores, key=lambda x: scores[x], reverse=True)
    ]

def mmr_rerank(
    chunks: List[Dict], 
    query_emb: List[float], 
    top_k: int, 
    lam: float = settings.MMR_LAMBDA
) -> List[Dict]:
    """Select chunks using Maximal Marginal Relevance (MMR) to balance relevance and diversity."""
    if not chunks or len(chunks) <= top_k:
        return chunks

    def get_emb(c: Dict) -> Optional[np.ndarray]:
        e = c.get("embedding")
        if e and isinstance(e, list):
            return np.array(e, dtype=float)
        return None

    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    q = np.array(query_emb, dtype=float)
    selected: List[Dict] = []
    remaining = list(chunks)

    while len(selected) < top_k and remaining:
        best_idx, best_score = 0, -float("inf")
        for i, c in enumerate(remaining):
            emb = get_emb(c)
            # Use cosine if embeddings present, fallback to raw similarity score
            rel = cosine(emb, q) if emb is not None else get_chunk_similarity(c)
            
            if not selected:
                score = rel
            else:
                max_sim = max(
                    (
                        cosine(emb, get_emb(s))
                        if (emb is not None and get_emb(s) is not None)
                        else 0.0
                    )
                    for s in selected
                )
                score = lam * rel - (1 - lam) * max_sim
            
            if score > best_score:
                best_score, best_idx = score, i
        
        selected.append(remaining.pop(best_idx))

    return selected


def rank_papers(papers: List[Dict], anchors: List[str]) -> List[Dict]:
    """Score and sort papers by relevance to the search anchors."""
    if not anchors:
        return papers

    def score(p: Dict) -> float:
        title = (p.get("title") or "").lower()
        s = 0.0
        for anchor in anchors:
            a = anchor.lower()
            if title == a:
                s += 100.0
            elif title.startswith(a) or a in title:
                s += 60.0
            else:
                t_words = set(title.split())
                a_words = set(a.split())
                overlap = len(t_words & a_words)
                s += overlap * 10.0
        # Base DB Score
        s += (p.get("score", 1) - 1) * 5.0

        # Recency Boost (Modern Papers)
        try:
            year = int(p.get("year", 2000))
            if year >= 2024:
                s += 40.0
            elif year >= 2017:
                s += 20.0
            else:
                s += max(0, (year - 2000)) * 0.5
        except (TypeError, ValueError):
            pass
            
        # High Impact / Citations Boost
        import math
        try:
            cits = int(p.get("citations", p.get("n_citation", 0)))
            s += math.log(cits + 1) * 15.0
        except (TypeError, ValueError):
            pass
            
        return s

    return sorted(papers, key=score, reverse=True)
