import asyncio
from typing import List, Dict, Optional, Any
from ..core.config import settings
from ..core.logging_config import log
from ..utils.cache import get_cache, set_cache, cache_key
from ..utils.ranking import rank_papers
from .pool import pool

async def retrieve_graph_papers(
    keywords: Optional[List[str]] = None,
    filters: Optional[Dict] = None,
    limit: int = settings.MAX_GRAPH_NODES,
    anchors: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Advanced Graph Retrieval Orchestrator:
    1. Seed: Finds papers matching keywords/authors.
    2. Expand: Explores 1-hop neighborhood (CITES, CITED_BY, co-authors).
    3. Union: Merges results with explicit relationship tracking for chronology.
    """
    if not pool.neo4j:
        return []

    safe_kw = (keywords or [])[:5]
    ck = cache_key("graph_unified_v2", str(safe_kw), str(filters), limit)
    cached = await get_cache("graph", ck)
    if cached:
        return cached

    # Construct filters
    yf = df = ""
    extra = {}
    if filters:
        if filters.get("year"):
            yf = "AND p.year = $year"
            extra["year"] = int(filters["year"])
        if filters.get("domain"):
            df = "AND toLower(p.domain) = toLower($domain)"
            extra["domain"] = filters["domain"]

    params: Dict[str, Any] = {"limit": limit, "keywords": safe_kw, **extra}

    async def _fetch(driver, store_label: str):
        # Dynamic Schema Validation
        s = pool.schema.get(store_label, {})
        has_written_by = "WRITTEN_BY" in s.get("rels", set())
        has_published_in = "PUBLISHED_IN" in s.get("rels", set())
        has_cites = "CITES" in s.get("rels", set())
        has_abstract = "abstract" in s.get("props", set())
        has_research_id = "research_id" in s.get("props", set())
        
        rid_prop = "research_id" if has_research_id else "id"
        abstract_val = "p.abstract" if has_abstract else "''"
        
        wb_clause = "MATCH (p)-[:WRITTEN_BY]->(a:Author) WHERE toLower(a.name) CONTAINS toLower(kw)" if has_written_by else "FALSE"
        
        # Enhanced query to return relationships for chronology linking
        s_q = f"""
        WITH $keywords AS kws UNWIND kws AS kw
        MATCH (p:Publication)
        WHERE (toLower(p.title) CONTAINS toLower(kw) OR EXISTS {{
            {wb_clause}
        }}) {yf} {df}
        WITH DISTINCT p
        OPTIONAL MATCH (p)-[:WRITTEN_BY]->(a) WHERE {str(has_written_by).upper()}
        OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v) WHERE {str(has_published_in).upper()}
        OPTIONAL MATCH (p)-[:CITES]->(ref:Publication) WHERE {str(has_cites).upper()}
        RETURN p.{rid_prop} AS research_id, p.title AS title, p.year AS year,
               {abstract_val} AS abstract,
               collect(DISTINCT a.name) AS authors, v.name AS venue,
               collect(DISTINCT ref.{rid_prop}) AS references,
               2 AS score
        ORDER BY p.year DESC LIMIT $limit
        """

        e_q = f"""
        WITH $keywords AS kws UNWIND kws AS kw
        MATCH (p:Publication)
        WHERE (toLower(p.title) CONTAINS toLower(kw) OR EXISTS {{
            {wb_clause}
        }}) {yf} {df}
        WITH collect(DISTINCT p) AS seeds UNWIND seeds AS seed
        OPTIONAL MATCH (seed)-[:CITES]->(cited:Publication) WHERE {str(has_cites).upper()}
        OPTIONAL MATCH (citing:Publication)-[:CITES]->(seed) WHERE {str(has_cites).upper()}
        WITH seeds, collect(DISTINCT cited) + collect(DISTINCT citing) AS expanded
        UNWIND expanded AS ep WITH DISTINCT ep, seeds WHERE ep IS NOT NULL AND NOT ep IN seeds
        OPTIONAL MATCH (ep)-[:WRITTEN_BY]->(a) WHERE {str(has_written_by).upper()}
        OPTIONAL MATCH (ep)-[:CITES]->(ref:Publication) WHERE {str(has_cites).upper()}
        RETURN ep.{rid_prop} AS research_id, ep.title AS title, ep.year AS year,
               {abstract_val if has_abstract else "''"} AS abstract,
               collect(DISTINCT a.name) AS authors, 
               collect(DISTINCT ref.{rid_prop}) AS references,
               1 AS score
        ORDER BY ep.year DESC LIMIT $limit
        """
        
        async with driver.session() as session:
            s_res = await session.run(s_q, params)
            s_rows = [dict(r) for r in await s_res.data()]
            e_res = await session.run(e_q, params)
            e_rows = [dict(r) for r in await e_res.data()]
            return s_rows, e_rows

    tasks = [_fetch(pool.neo4j, "A")]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    seen, merged = set(), []
    for res in results:
        if isinstance(res, tuple):
            s_rows, e_rows = res
            for row in s_rows + e_rows:
                rid = row.get("research_id")
                if rid and rid not in seen:
                    seen.add(rid)
                    merged.append(row)

    ranked = rank_papers(merged, anchors or keywords or [])
    result = ranked[:limit]
    await set_cache("graph", ck, result)
    return result

async def get_paper_full(paper_id: str) -> Optional[Dict]:
    """Retrieve full unified graph node with all neighbors from both stores."""
    ck = cache_key("paper_full", paper_id)
    cached = await get_cache("relations", ck)
    if cached:
        return cached

    async def _run(driver, store_label):
        if not driver: return []
        
        pub_label = "Publication" if store_label == "A" else "ArXivPaper"
        
        # Check if the label exists in this store
        s = pool.schema.get(store_label, {})
        if pub_label not in s.get("labels", set()):
            return []

        has_written_by = "WRITTEN_BY" in s.get("rels", set())
        has_published_in = "PUBLISHED_IN" in s.get("rels", set())
        has_cites = "CITES" in s.get("rels", set())
        
        rid_prop = "research_id" if "research_id" in s.get("props", set()) else "id"
        abstract_prop = "p.abstract" if "abstract" in s.get("props", set()) else "''"
        url_prop = "p.url" if "url" in s.get("props", set()) else "''"

        q = f"""
        MATCH (p:{pub_label})
        WHERE p.{rid_prop} = $pid OR p.id = $pid OR toLower(p.title) CONTAINS toLower($pid)
        WITH p LIMIT 1
        OPTIONAL MATCH (p)-[:WRITTEN_BY]->(a:Author) WHERE {str(has_written_by).upper()}
        OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v:Venue) WHERE {str(has_published_in).upper()}
        OPTIONAL MATCH (p)-[:CITES]->(out:{pub_label}) WHERE {str(has_cites).upper()}
        OPTIONAL MATCH (p)<-[:CITES]-(in_p:{pub_label}) WHERE {str(has_cites).upper()}
        RETURN p.{rid_prop} AS research_id, p.title AS title, p.year AS year,
               {abstract_prop} AS abstract, {url_prop} AS url,
               collect(DISTINCT a.name) AS authors, v.name AS venue,
               collect(DISTINCT out.title) AS references,
               collect(DISTINCT in_p.title) AS cited_by
        """
        
        async with driver.session() as session:
            res = await session.run(q, {"pid": paper_id})
            return [dict(r) for r in await res.data()]

    tasks = [_run(pool.neo4j, "A")]
    if pool.arxiv_neo4j_ok:
        tasks.append(_run(pool.arxiv_neo4j, "B"))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_rows = []
    for r in results:
        if isinstance(r, list): all_rows.extend(r)
    
    if not all_rows: return None
    best = max(all_rows, key=lambda x: len(x.get("authors", [])))
    await set_cache("relations", ck, best)
    return best

async def get_author_network(author_name: str) -> Dict:
    """Get an author's ego-network: papers, co-authors, venues."""
    if not pool.neo4j:
        return {}

    ck = cache_key("author", author_name)
    cached = await get_cache("relations", ck)
    if cached:
        return cached

    cypher = """
    MATCH (a:Author)
    WHERE toLower(a.name) CONTAINS toLower($name)
    WITH a LIMIT 1
    OPTIONAL MATCH (a)<-[:WRITTEN_BY]-(p:Publication)
    OPTIONAL MATCH (p)-[:WRITTEN_BY]->(coauthor:Author)
    WHERE coauthor <> a
    OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v:Venue)
    RETURN a.name           AS author_name,
           a.affiliation    AS affiliation,
           collect(DISTINCT {title: p.title, year: p.year, domain: p.domain}) AS papers,
           collect(DISTINCT coauthor.name)  AS coauthors,
           collect(DISTINCT v.name)         AS venues,
           count(DISTINCT p)                AS paper_count
    """
    try:
        async with pool.neo4j.session() as session:
            res = await session.run(cypher, {"name": author_name})
            rows = await res.data()
            result = dict(rows[0]) if rows else {}
            await set_cache("relations", ck, result)
            return result
    except Exception as e:
        log.warning(f"get_author_network error: {e}")
        return {}

async def get_citation_path(from_title: str, to_title: str, max_depth: int = 4) -> Dict:
    """Find shortest citation path between two papers."""
    if not pool.neo4j:
        return {}

    cypher = f"""
    MATCH (a:Publication), (b:Publication)
    WHERE toLower(a.title) CONTAINS toLower($from_title)
      AND toLower(b.title) CONTAINS toLower($to_title)
    WITH a, b LIMIT 1
    MATCH path = shortestPath((a)-[:CITES*..{max_depth}]->(b))
    RETURN [node IN nodes(path) | node.title] AS path_titles,
           length(path) AS path_length
    LIMIT 1
    """
    try:
        async with pool.neo4j.session() as session:
            res = await session.run(cypher, {"from_title": from_title, "to_title": to_title})
            rows = await res.data()
            return dict(rows[0]) if rows else {"path_titles": [], "path_length": -1}
    except Exception as e:
        log.warning(f"get_citation_path error: {e}")
        return {"path_titles": [], "path_length": -1, "error": str(e)}

async def get_trending_papers(limit: int = 10) -> List[Dict]:
    """Identify 'trending' papers based on citation velocity (recent citations).

    Uses CITES relationship if available (real trending).
    Falls back to recency-only if the relationship doesn't exist in this store.
    """
    if not pool.neo4j:
        return []

    has_cites = "CITES" in pool.schema.get("A", {}).get("rels", set())

    if has_cites:
        # Citation-velocity: count how many papers written in the last 2 years cite each paper
        cypher = """
        MATCH (citing:Publication)-[:CITES]->(p:Publication)
        WHERE citing.year >= date().year - 2
        WITH p, count(citing) AS recent_citations
        WHERE recent_citations > 0
        RETURN p.title AS title, p.year AS year, recent_citations AS citations
        ORDER BY recent_citations DESC, p.year DESC
        LIMIT $limit
        """
    else:
        # Fallback: recency-only (no CITES in this store)
        cypher = """
        MATCH (p:Publication)
        RETURN p.title AS title, p.year AS year, 0 AS citations
        ORDER BY p.year DESC
        LIMIT $limit
        """

    try:
        async with pool.neo4j.session() as session:
            res = await session.run(cypher, {"limit": limit})
            rows = [dict(r) for r in await res.data()]
            # If citation query returned nothing (e.g. year function issue), retry with recency
            if has_cites and not rows:
                fallback = """
                MATCH (citing:Publication)-[:CITES]->(p:Publication)
                WITH p, count(citing) AS citations
                RETURN p.title AS title, p.year AS year, citations
                ORDER BY citations DESC, p.year DESC
                LIMIT $limit
                """
                res2 = await session.run(fallback, {"limit": limit})
                rows = [dict(r) for r in await res2.data()]
            return rows
    except Exception as e:
        log.warning(f"get_trending_papers error: {e}")
        return []

def generate_mermaid_graph(papers: List[Dict]) -> str:
    """Generate Mermaid.js syntax for a citation/co-authorship network."""
    if not papers:
        return ""

    lines = ["graph TD"]
    # 1. Define nodes (shortened titles)
    seen_ids = set()
    for p in papers:
        pid = p.get("research_id") or p.get("id") or p.get("source_id")
        if not pid: continue
        
        # Sanitize title for Mermaid
        title = p.get("title", "Unknown")
        title_short = (title[:30] + "...") if len(title) > 33 else title
        title_clean = title_short.replace('"', "'").replace("(", "[").replace(")", "]")
        
        # Node definition: ID["Title (Year)"]
        year = p.get("year", "?")
        lines.append(f'    {pid}["{title_clean} ({year})"]')
        seen_ids.add(pid)

    # 2. Define relationships (CITES)
    for p in papers:
        pid = p.get("research_id") or p.get("id") or p.get("source_id")
        refs = p.get("references") or []
        for ref_id in refs:
            if ref_id in seen_ids:
                lines.append(f"    {pid} --> {ref_id}")

    # 3. Define co-authorship clusters (optional but adds value)
    # For simplicity, we just link papers by same authors
    author_map = {}
    for p in papers:
        pid = p.get("research_id") or p.get("id") or p.get("source_id")
        authors = p.get("authors") or []
        for author in authors:
            if author not in author_map:
                author_map[author] = []
            author_map[author].append(pid)

    for author, paper_ids in author_map.items():
        if len(paper_ids) > 1:
            # Connect papers by same author with a dotted line
            for i in range(len(paper_ids) - 1):
                lines.append(f"    {paper_ids[i]} -.- {paper_ids[i+1]}")

    return "\n".join(lines)
