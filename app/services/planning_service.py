import json
import re
from typing import Any
from ..core.config import settings
from ..core.logging_config import log
from ..core.models import QueryPlan
from ..core.exceptions import LLMError
from ..utils.cache import get_cache, set_cache, cache_key
from .llm import groq_chat

SUPER_MASTER_PROMPT = """\
You are the Strategic Planning Brain for Aether, an evidence-only GraphRAG Research Assistant.
Decompose the user query into a precise execution plan.

━━━ INPUT ━━━
USER QUERY: {query}
CONVERSATION HISTORY (last 3 turns):
{context}

━━━ STEPS ━━━

STEP 1 - RESOLVE PRONOUNS
If the query contains "it", "they", "this paper", "the authors", or similar ambiguity:
  Identify the referent from CONVERSATION HISTORY and rewrite the query to be self-contained.
  If unresolvable, set "ambiguous": true.

STEP 2 - CLASSIFY ROUTE (pick exactly one):
  "entity_lookup"  -> factual metadata query: author, year, domain, venue, affiliation.
  "structured"     -> list/filter: list papers, find papers on X, papers by author Y.
  "title_lookup"   -> user names a specific paper and wants its record only.
  "compare"        -> side-by-side of 2+ papers, methods, or approaches.
  "timeline"       -> chronological evolution of a topic across years.
  "survey"         -> broad synthesis of a research area.
  "rag"            -> explanation, analysis, synthesis of concepts.
  "gap_analysis"   -> ✨NEW: Identifying unaddressed research questions or limitations across papers.
  "methodology_validation" -> ✨NEW: Analyzing, critiquing, or validating research methodologies.
  "chitchat"       -> social or basic 101 definitions: "what is X?", greeting, thanks. Always pick this for basic definitions or general non-research talk.
  "deep_research"  -> ✨NEW: Fetch NEWEST papers from ArXiv MCP before answering.
  "ingest"         -> ✨NEW: Explicitly search and SAVE a paper to Store B.
  "trending"       -> ✨NEW: Show trending topics/papers in Store B.

STEP 3 - EXTRACT GRAPH ANCHORS
  1-3 minimal paper title substrings or author names for Neo4j lookup.

STEP 4 - EXTRACT VECTOR KEYWORDS
  Extract 2-4 core multi-word concepts (e.g., "machine learning", "neural networks") from the query. These will be used for exact-match searches. Do not use generic single words unless necessary.

STEP 5 - DOMAIN CLASSIFICATION
  Identify the specific ArXiv category (e.g., "cs.AI", "cs.LG", "cs.MA", "cs.CV", "cs.RO", "cs.CL"). If unsure, use "unknown".

STEP 6 - REASONING PATH
  One sentence describing the assembly strategy.

STEP 7 - ARXIV QUERY BUILDING (Optional)
If the query involves specific author/title/category combinations, suggest keywords for build_advanced_query.

STEP 8 - QUERY UNDERSTANDING
Analyze the core domain (e.g. "machine_learning", "biology", "physics") and the intent (e.g. "research_overview", "methodology_comparison", "state_of_the_art"). This helps retrieve high-impact papers.

━━━ OUTPUT FORMAT ━━━
Respond ONLY with a valid JSON object.

{{
  "standalone_query": "<self-contained rewrite>",
  "intent": "<research intent>",
  "domain": "<core topic domain>",
  "ambiguous": false,
  "route": "<route_name>",
  "graph_anchors": ["<minimal anchor>"],
  "vector_keywords": ["<term>"],
  "required_metrics": ["<metric>"],
  "reasoning_path": "<one sentence>",
  "cache_key": "<lowercase stripped>",
  "advanced_query_params": {{
    "title_keywords": "<title>",
    "author_name": "<author>",
    "category": "<arxiv_cat>"
  }}
}}
"""

async def plan_query(query: str, context: str = "") -> QueryPlan:
    """Analyze query intent and generate a structured execution plan."""
    ck = cache_key("plan", query, context[:200])
    cached = await get_cache("plan", ck)
    if cached:
        log.debug("Plan cache hit")
        if isinstance(cached, dict):
            return QueryPlan(**cached)
        return cached

    prompt = SUPER_MASTER_PROMPT.format(query=query, context=context or "None")
    try:
        raw_text = await groq_chat(
            [{"role": "user", "content": prompt}],
            settings.PLAN_MODEL,
            temperature=0.0,
            max_tokens=400,
            json_mode=True,
        )
        data = json.loads(raw_text.strip())
    except (LLMError, json.JSONDecodeError, Exception) as e:
        log.warning(f"Plan failed ({e}), using fallback")
        data = {}

    plan = QueryPlan(
        standalone_query=data.get("standalone_query", query),
        route=data.get("route", "rag"),
        graph_anchors=data.get("graph_anchors", [])[:3],
        vector_keywords=data.get("vector_keywords", [])[:5],
        required_metrics=data.get("required_metrics", []),
        reasoning_path=data.get("reasoning_path", ""),
        intent=data.get("intent", ""),
        domain=data.get("domain", ""),
        ambiguous=data.get("ambiguous", False),
        cache_key_str=data.get("cache_key", re.sub(r"[^\w\s]", "", query.lower())),
        advanced_query_params=data.get("advanced_query_params", {}),
        raw=data,
    )
    
    from dataclasses import asdict
    await set_cache("plan", ck, asdict(plan))
    log.info(f"Plan: route={plan.route} anchors={plan.graph_anchors} kw={plan.vector_keywords}")
    return plan
