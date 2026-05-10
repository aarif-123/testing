import json
from typing import List, Dict, Any, Optional
from ..core.config import settings
from ..core.logging_config import log
from .llm import groq_chat

CRITIC_PROMPT = """\
You are the Quality Control Agent for Aether, an advanced GraphRAG Research Assistant.
Your task is to evaluate the completeness and grounding of the current research state.

━━━ INPUT ━━━
QUERY: {query}
CONTEXT CHUNKS: {chunks_count}
GRAPH NODES: {nodes_count}
CURRENT DRAFT ANSWER: {draft}

━━━ EVALUATION CRITERIA ━━━
1. GROUNDING: Does the draft answer every part of the query using ONLY the provided context?
2. SUFFICIENCY: Is there enough information to provide a definitive answer? 
3. PRECISION: Are there specific metrics, dates, or methodologies mentioned?
4. GAPS: Identify any specific technical details or "missing hops" that are still needed.

━━━ OUTPUT FORMAT ━━━
Respond ONLY with a valid JSON object.

{{
  "sufficient": true/false,
  "confidence_score": 0.0-1.0,
  "detected_gaps": ["gap 1", "gap 2"],
  "re_plan_required": true/false,
  "suggestion": "Specific instructions for the next search pass, e.g., 'Search for the specific accuracy of Model X on Dataset Y'"
}}
"""

class CriticService:
    async def evaluate_research(
        self, query: str, chunks: List[Dict], nodes: List[Dict], draft: str
    ) -> Dict[str, Any]:
        """Evaluate if the current research state is sufficient to answer the query."""
        log.info(f"Critiquing research state for: {query[:50]}...")
        
        prompt = CRITIC_PROMPT.format(
            query=query,
            chunks_count=len(chunks),
            nodes_count=len(nodes),
            draft=draft[:1000] # Truncate draft for efficiency
        )
        
        try:
            raw_text = await groq_chat(
                [{"role": "user", "content": prompt}],
                settings.PLAN_MODEL, # Use the fast model for critique
                temperature=0.0,
                json_mode=True
            )
            return json.loads(raw_text.strip())
        except Exception as e:
            log.error(f"Critic Agent failed: {e}")
            return {
                "sufficient": True, # Fallback to avoid infinite loops
                "confidence_score": 0.5,
                "detected_gaps": [],
                "re_plan_required": False,
                "suggestion": ""
            }

critic_service = CriticService()
