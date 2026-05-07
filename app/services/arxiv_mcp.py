import asyncio
import contextlib
import uuid
import re
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ..core.logging_config import log


class ArXivMCPService:
    """
    ArXiv MCP client with a warm persistent Docker session.

    Instead of spinning up a new Docker container per request (2-5s cold start),
    we keep one warm session alive and reconnect only on failure. A lock ensures
    only one request can use the session at a time (MCP stdio is inherently serial).
    """

    def __init__(self):
        self.server_params = StdioServerParameters(
            command="docker",
            args=[
                "run",
                "-i",
                "--rm",
                "ghcr.io/tejas242/arxiv-mcp:latest"
            ]
        )
        self._session: ClientSession | None = None
        self._cm_stack: contextlib.AsyncExitStack | None = None
        self._lock = asyncio.Lock()
        self._warming = False

    async def _get_session(self) -> ClientSession | None:
        """Return the warm session, reconnecting if needed."""
        if self._session is not None:
            return self._session
        try:
            log.info("[ArXivMCP] Warming up persistent Docker session...")
            self._cm_stack = contextlib.AsyncExitStack()
            read, write = await self._cm_stack.enter_async_context(
                stdio_client(self.server_params)
            )
            session = await self._cm_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self._session = session
            log.info("[ArXivMCP] Persistent session ready.")
            return self._session
        except Exception as e:
            log.error(f"[ArXivMCP] Failed to warm session: {e}")
            self._session = None
            if self._cm_stack:
                await self._cm_stack.aclose()
                self._cm_stack = None
            return None

    async def _invalidate_session(self):
        """Close and discard the broken session so the next call rebuilds it."""
        self._session = None
        if self._cm_stack:
            try:
                await self._cm_stack.aclose()
            except Exception:
                pass
            self._cm_stack = None

    async def search_papers(self, query: str, limit: int = 5):
        """Search for papers on arXiv using the MCP tool."""
        async with self._lock:
            session = await self._get_session()
            if session is None:
                return []
            try:
                result = await session.call_tool(
                    "search_papers",
                    arguments={
                        "query": query,
                        "max_results": limit,
                        "sort_by": "relevance",
                        "sort_order": "descending"
                    }
                )
                if hasattr(result, 'content') and isinstance(result.content, list):
                    return result.content
                return result
            except Exception as e:
                log.error(f"[ArXivMCP] search_papers failed, invalidating session: {e}")
                await self._invalidate_session()
                return []

    async def list_papers(self):
        """List locally available/cached papers via MCP."""
        async with self._lock:
            session = await self._get_session()
            if session is None:
                return []
            try:
                result = await session.call_tool("list_papers", arguments={})
                if hasattr(result, 'content') and isinstance(result.content, list):
                    return result.content
                return result
            except Exception as e:
                log.error(f"[ArXivMCP] list_papers failed: {e}")
                await self._invalidate_session()
                return []

    async def read_paper(self, arxiv_id: str):
        """Read the full text/content of an arXiv paper via MCP. Fallback to get_paper_details."""
        async with self._lock:
            session = await self._get_session()
            if session is None:
                return None
            try:
                result = await session.call_tool(
                    "get_paper_details",
                    arguments={"arxiv_id": arxiv_id}
                )
                return result
            except Exception as e:
                log.error(f"[ArXivMCP] read_paper (get_paper_details) failed: {e}")
                await self._invalidate_session()
                return None

    async def download_paper(self, arxiv_id: str):
        """Download an arXiv paper via MCP."""
        async with self._lock:
            session = await self._get_session()
            if session is None:
                return None
            try:
                result = await session.call_tool(
                    "download_paper",
                    arguments={"arxiv_id": arxiv_id}
                )
                return result
            except Exception as e:
                log.error(f"[ArXivMCP] download_paper failed: {e}")
                await self._invalidate_session()
                return None

    async def get_details(self, arxiv_id: str):
        """Get full details/abstract for a specific arXiv ID by directly querying arXiv API to bypass MCP truncation."""
        import urllib.request
        import xml.etree.ElementTree as ET
        try:
            url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, urllib.request.urlopen, req)
            data = response.read().decode('utf-8')
            root = ET.fromstring(data)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entry = root.find('atom:entry', ns)
            if entry is not None:
                summary = entry.find('atom:summary', ns)
                if summary is not None:
                    # Return a fake MCP result object that format_for_db can parse
                    # Or just return the raw string we can format
                    return f"**Abstract:**\n{summary.text.strip()}\n\n"
            return None
        except Exception as e:
            log.error(f"[ArXivMCP] get_details native fetch failed: {e}")
            return None

    async def close(self):
        """Gracefully close the persistent session on shutdown."""
        await self._invalidate_session()
        log.info("[ArXivMCP] Session closed.")

    def parse_multiple_papers(self, raw_text) -> list[dict]:
        """Splits the bulk Markdown string from ArXiv MCP into individual paper dicts."""
        if hasattr(raw_text, 'text'):
            raw_text = getattr(raw_text, 'text')
        elif isinstance(raw_text, dict) and 'text' in raw_text:
            raw_text = raw_text['text']
        elif not isinstance(raw_text, str):
            raw_text = str(raw_text)

        papers = []
        parts = re.split(r'\n\d+\.\s+\*\*', raw_text)

        for part in parts[1:]:
            part = "**" + part
            parsed = self.format_for_db(part)
            if parsed.get("source_id"):
                papers.append(parsed)

        if not papers and "**" in raw_text:
            parsed = self.format_for_db(raw_text)
            if parsed.get("source_id"):
                papers.append(parsed)

        return papers

    def format_for_db(self, raw_text: str) -> dict:
        """Parses the Markdown/Text output from the ArXiv MCP server into a structured dict."""
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
            # Handle MCP TextContent objects
            if hasattr(raw_text, 'text'):
                raw_text = getattr(raw_text, 'text')
            elif isinstance(raw_text, dict) and 'text' in raw_text:
                raw_text = raw_text['text']
            elif not isinstance(raw_text, str):
                raw_text = str(raw_text)

            # 1. Title
            title_match = re.search(r'^\*\*(.*?)\*\*', raw_text, re.MULTILINE)
            if title_match:
                data["title"] = title_match.group(1).strip()
            else:
                lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                if lines:
                    data["title"] = lines[0].strip('* ')

            # 2. ArXiv ID
            id_match = re.search(
                r'(?:arxiv[:\s]*)?([\d]{4}\.[\d]{4,5}v?[\d]*)', raw_text, re.IGNORECASE
            )
            if id_match:
                aid = id_match.group(1).strip()
                data["source_id"] = aid
                data["global_entity_id"] = f"arxiv:{aid}"
                data["url"] = f"https://arxiv.org/abs/{aid}"

            # 3. Authors
            author_regex = r'(?i)\*?\*?Authors?:?\*?\*?\s+(.*?)(?:\n|$)'
            author_match = re.search(author_regex, raw_text)
            if author_match:
                author_text = author_match.group(1).strip()
                author_text = re.sub(r'\s*et al\..*', '', author_text)
                author_text = re.sub(r'\(.*?\)', '', author_text)
                data["authors"] = [a.strip() for a in author_text.split(',') if a.strip()]

            # 4. Published Date
            date_match = re.search(r'\*\*Published:\*\*\s*(\d{4}-\d{2}-\d{2})', raw_text)
            if date_match:
                data["published"] = date_match.group(1)
                data["year"] = int(date_match.group(1).split('-')[0])

            # 5. Category
            cat_regex = r'(?:\*?\*?(?:Primary )?Category(?:\(ies\))?:?\*?\*?\s*)(.*?)(?:\n|$)'
            cat_match = re.search(cat_regex, raw_text, flags=re.IGNORECASE)
            if cat_match:
                data["categories"] = [cat_match.group(1).strip()]

            # 6. Abstract
            abstract_match = re.search(r'(?i)\*?\*?Abstract:\*?\*?\s*(.*?)(?=\n\s*(?:PDF:|\*\*Links:\*\*|Note:|arXiv ID:|\Z))', raw_text, re.DOTALL)
            if abstract_match:
                data["abstract"] = abstract_match.group(1).strip()
            else:
                data["abstract"] = ""

            # 7. UUID
            namespace = uuid.NAMESPACE_DNS
            if data["source_id"]:
                data["id"] = str(uuid.uuid5(namespace, f"arxiv:{data['source_id']}"))
            else:
                data["id"] = str(uuid.uuid5(namespace, data["title"]))

        except Exception as e:
            log.error(f"Failed to parse MCP output: {e}")

        return data


# Singleton instance
arxiv_mcp = ArXivMCPService()
