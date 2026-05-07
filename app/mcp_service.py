import asyncio
import logging
from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


log = logging.getLogger("graphrag.mcp")


class ArXivMCPService:
    def __init__(self):
        import time
        # Parameters to run the arXiv MCP server via Docker
        self.server_params = StdioServerParameters(
            command="docker",
            args=[
                "run",
                "-i",
                "--rm",
                "ghcr.io/tejas242/arxiv-mcp:latest"
            ]
        )
        self.session = None
        self.stdio_cm = None
        self.session_cm = None
        self.last_used = time.time()
        self._lock = asyncio.Lock()

    async def ensure_session(self):
        import time
        async with self._lock:
            # check idle timeout of 5 minutes
            if self.session and time.time() - self.last_used > 300:
                log.info("Closing idle arXiv MCP session")
                await self.close_session()

            if not self.session:
                try:
                    log.info("Initializing long-lived arXiv MCP session...")
                    self.stdio_cm = stdio_client(self.server_params)
                    read, write = await self.stdio_cm.__aenter__()
                    self.session_cm = ClientSession(read, write)
                    self.session = await self.session_cm.__aenter__()
                    await self.session.initialize()
                    log.info("arXiv MCP session initialized successfully.")
                except Exception as e:
                    log.error(f"Failed to initialize long-lived MCP session: {e}")
                    self.session = None

            self.last_used = time.time()
            return self.session

    async def close_session(self):
        if self.session:
            try:
                await self.session_cm.__aexit__(None, None, None)
                await self.stdio_cm.__aexit__(None, None, None)
            except Exception as e:
                log.error(f"Error while exiting MCP session: {e}")
            self.session = None
            self.session_cm = None
            self.stdio_cm = None

    async def search_papers(self, query: str, max_results: int = 5, sort_by: str = "relevance"):
        """Search for papers on arXiv using the MCP tool."""
        try:
            session = await self.ensure_session()
            if not session:
                return []
            log.info(f"Connecting to arXiv MCP for search: {query}")
            async with self._lock:
                result = await session.call_tool(
                    "search_papers",
                    arguments={
                        "query": query,
                        "max_results": max_results,
                        "sort_by": sort_by
                    }
                )
                self.last_used = time.time()
                if hasattr(result, 'content') and isinstance(result.content, list):
                    return result.content
                return result
        except Exception as e:
            log.error(f"MCP Search failed: {e}")
            return []

    async def get_details(self, arxiv_id: str):
        """Get full details/abstract for a specific arXiv ID."""
        try:
            session = await self.ensure_session()
            if not session:
                return None
            log.info(f"Connecting to arXiv MCP for details: {arxiv_id}")
            async with self._lock:
                result = await session.call_tool(
                    "get_paper_details",
                    arguments={"arxiv_id": arxiv_id}
                )
                self.last_used = time.time()
                return result
        except Exception as e:
            log.error(f"MCP Details failed: {e}")
            return None

    async def build_query(self, **kwargs):
        """Advanced query builder using MCP."""
        try:
            session = await self.ensure_session()
            if not session:
                return None
            async with self._lock:
                result = await session.call_tool(
                    "build_advanced_query",
                    arguments=kwargs
                )
                self.last_used = time.time()
                if hasattr(result, 'content') and result.content:
                    return result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                return str(result)
        except Exception as e:
            log.error(f"Query builder failed: {e}")
            return None

    def format_for_db(self, raw_input: Any) -> list[dict]:
        """
        Parses Markdown/Text output from ArXiv MCP into a list of structured dicts.
        Handles bulk responses containing multiple papers.
        """
        import uuid
        import re

        # extraction context
        raw_text = ""
        if hasattr(raw_input, 'text'):
            raw_text = raw_input.text
        elif isinstance(raw_input, dict) and 'text' in raw_input:
            raw_text = raw_input['text']
        elif isinstance(raw_input, str):
            raw_text = raw_input
        else:
            raw_text = str(raw_input)

        # Split bulk response into individual paper blocks
        # Pattern: "1. **Title**", "2. **Title**", etc.
        blocks = re.split(r'\n\n\d+\. \*\*', "\n\n" + raw_text)
        # First block is usually a header ("Found X papers..."), skip it if it doesn't look like a paper
        paper_results = []

        for block in blocks:
            if not block.strip() or "**" not in block:
                continue
            
            # Clean up the block prefix if it was split
            block = block.lstrip('1234567890. *')

            data = {
                "id": None,
                "source_store": "arxiv",
                "source_id": None,
                "global_entity_id": None,
                "title": "Unknown Title",
                "abstract": "",
                "authors": [],
                "year": 2025,
                "published": None,
                "url": None,
                "categories": [],
                "n_citation": 0
            }

            try:
                # 1. Title: top of the block
                title_match = re.search(r'^\s*(.*?)(?:\*\*|$)', block)
                if title_match:
                    data["title"] = title_match.group(1).strip()
                
                # 2. ArXiv ID -> source_id (Capture versioned IDs like 2211.02350v1)
                id_match = re.search(r'\s*arXiv ID:\s*([\d\.]+v?\d*)', block, re.IGNORECASE)
                if id_match:
                    aid = id_match.group(1).strip()
                    data["source_id"] = aid
                    data["global_entity_id"] = f"arxiv:{aid}"
                    data["url"] = f"https://arxiv.org/abs/{aid}"

                # 3. Authors
                author_regex = r'\s*Authors:\s*(.*?)(?:\n|$)'
                author_match = re.search(author_regex, block, re.IGNORECASE)
                if author_match:
                    author_text = author_match.group(1).strip()
                    author_text = re.sub(r'et al\..*', '', author_text)
                    author_text = re.sub(r'\(.*?\)', '', author_text)
                    data["authors"] = [a.strip() for a in author_text.split(',') if a.strip()]

                # 4. Published Date
                date_match = re.search(r'\s*Published:\s*(\d{4}-\d{2}-\d{2})', block, re.IGNORECASE)
                if date_match:
                    data["published"] = date_match.group(1)
                    data["year"] = int(date_match.group(1).split('-')[0])

                # 5. Category
                cat_regex = r'\s*(?:Primary )?Category:\s*(.*?)(?:\n|$)'
                cat_match = re.search(cat_regex, block, re.IGNORECASE)
                if cat_match:
                    data["categories"] = [cat_match.group(1).strip()]

                # 6. Abstract
                # Extract everything after "Abstract:" until the next common field or end
                abs_regex = r'\s*Abstract:\s*(.*?)(?:\n\n|\nPDF:|\nCategories:|$)'
                abs_match = re.search(abs_regex, block, re.DOTALL | re.IGNORECASE)
                if abs_match:
                    data["abstract"] = abs_match.group(1).strip()

                # 7. Generate UUID
                if data["source_id"]:
                    data["id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"arxiv:{data['source_id']}"))
                else:
                    data["id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, data["title"]))

                if data["source_id"] or data["title"] != "Unknown Title":
                    paper_results.append(data)

            except Exception as e:
                log.error(f"Failed to parse paper block: {e}")

        return paper_results


# Singleton instance
arxiv_mcp = ArXivMCPService()
