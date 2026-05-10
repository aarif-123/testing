import aiohttp
from typing import List, Dict, Any, Optional
from ..core.config import settings
from ..core.logging_config import log

class WebSearchService:
    """
    Advanced Web Discovery Service (2026 Standard).
    Designed for deep research with support for Tavily or Serper.
    """
    def __init__(self):
        self.api_key = getattr(settings, "TAVILY_API_KEY", None)
        self.base_url = "https://api.tavily.com/search"

    async def search(self, query: str, search_depth: str = "advanced", max_results: int = 5) -> List[Dict[str, Any]]:
        """Perform an autonomous web search to find recent context outside ArXiv."""
        if not self.api_key:
            log.warning("WebSearchService: TAVILY_API_KEY not configured. Falling back to mock results.")
            return self._get_mock_results(query)

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": True,
            "include_raw_content": False
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._process_results(data.get("results", []))
                    else:
                        text = await resp.text()
                        log.error(f"WebSearch API Error [{resp.status}]: {text}")
                        return []
        except Exception as e:
            log.error(f"WebSearch execution failure: {e}")
            return []

    def _process_results(self, results: List[Dict]) -> List[Dict]:
        processed = []
        for r in results:
            processed.append({
                "title": r.get("title", "Web Source"),
                "url": r.get("url"),
                "content": r.get("content", ""),
                "score": r.get("score", 0.5),
                "source": "web"
            })
        return processed

    def _get_mock_results(self, query: str) -> List[Dict]:
        """Mock results for development when API key is missing."""
        return [
            {
                "title": f"Recent developments in {query} (2026 Survey)",
                "url": "https://example.com/research/2026",
                "content": f"Global research in {query} has shifted towards agentic orchestration and self-correcting RAG pipelines as seen in recent industry implementations.",
                "score": 0.95,
                "source": "web-discovery"
            }
        ]

web_search_service = WebSearchService()
