import asyncio
import threading
from neo4j import AsyncGraphDatabase
import httpx
from supabase import create_client

from ..core.config import settings
from ..core.logging_config import log

_supabase_local = threading.local()

def get_supabase_client():
    """Thread-safe Supabase client accessor."""
    if not hasattr(_supabase_local, "client"):
        url = settings.SUPABASE_URL
        key = settings.SUPABASE_KEY
        _supabase_local.client = create_client(url, key)
    return _supabase_local.client

class DualPool:
    """Manages connections to both DBLP (Store A) and ArXiv (Store B)."""

    def __init__(self):
        # Store A
        self.supabase = None
        self.async_supabase = None
        self.neo4j = None
        self.neo4j_ok = False
        # Store B
        self.arxiv_supabase = None
        self.arxiv_async_supabase = None
        self.arxiv_neo4j = None
        self.arxiv_neo4j_ok = False
        self.store_b_ok = False
        # Schema Metadata (Avoids Neo4j Warnings)
        self.schema = {
            "A": {"labels": set(), "rels": set(), "props": set()},
            "B": {"labels": set(), "rels": set(), "props": set()}
        }
        # Shared
        self.groq_http = None
        self.embed_http = None

    async def _connect_supabase(self, url: str, key: str, label: str):
        try:
            # Sync client for legacy support
            client = create_client(url, key)
            # Async client for performance with SSL bypass
            try:
                from supabase._async.client import AsyncClientOptions
                opt = AsyncClientOptions(httpx_client=httpx.AsyncClient(verify=False))
            except ImportError:
                # Fallback for older supabase versions
                from supabase import ClientOptions
                opt = ClientOptions(httpx_client=httpx.AsyncClient(verify=False))
            from supabase import create_async_client
            async_client = await create_async_client(url, key, options=opt)
            log.info(f"[bold green]Connected[/bold green] - {label} Supabase")
            return client, async_client
        except Exception as e:
            log.warning(f"[bold red]Failed[/bold red] - {label} Supabase: {e}")
            return None, None

    async def _connect_neo4j(self, uri: str, user: str, pwd: str, label: str):
        try:
            driver = AsyncGraphDatabase.driver(uri, auth=(user, pwd))
            await asyncio.wait_for(
                driver.verify_connectivity(),
                timeout=10.0,
            )
            # Fetch Schema Metadata
            async def _get_schema():
                async with driver.session() as s:
                    l_res = await s.run("CALL db.labels()")
                    l = await l_res.value()
                    r_res = await s.run("CALL db.relationshipTypes()")
                    r = await r_res.value()
                    p_res = await s.run("CALL db.propertyKeys()")
                    p = await p_res.value()
                    return set(l), set(r), set(p)
            
            l, r, p = await _get_schema()
            store_key = "A" if "StoreA" in label else "B"
            self.schema[store_key]["labels"] = l
            self.schema[store_key]["rels"] = r
            self.schema[store_key]["props"] = p
            
            log.info(f"{label} Neo4j connected (Schema: {len(l)} labels, {len(r)} rels)")
            return driver
        except Exception as e:
            log.warning(f"{label} Neo4j unavailable ({label}): {e}")
            return None

    async def init(self) -> None:
        # Init Store A
        self.supabase, self.async_supabase = await self._connect_supabase(
            settings.SUPABASE_URL, settings.SUPABASE_KEY, "[StoreA]"
        )
        self.neo4j = await self._connect_neo4j(
            settings.NEO4J_URI, 
            settings.NEO4J_USER, 
            settings.NEO4J_PASSWORD, 
            "[StoreA]"
        )
        self.neo4j_ok = self.neo4j is not None

        # Init Store B
        if settings.STORE_B_ENABLED:
            self.arxiv_supabase, self.arxiv_async_supabase = \
                await self._connect_supabase(
                    settings.ARXIV_SUPABASE_URL, 
                    settings.ARXIV_SUPABASE_KEY, 
                    "[StoreB]"
                )
            if settings.ARXIV_NEO4J_URI:
                self.arxiv_neo4j = await self._connect_neo4j(
                    settings.ARXIV_NEO4J_URI,
                    settings.ARXIV_NEO4J_USER,
                    settings.ARXIV_NEO4J_PASSWORD,
                    "[StoreB]",
                )
                self.arxiv_neo4j_ok = self.arxiv_neo4j is not None
            self.store_b_ok = self.arxiv_supabase is not None
            if self.store_b_ok:
                status = "operational" if self.arxiv_neo4j_ok else "degraded"
                log.info(f"Store B (ArXiv) is [bold cyan]{status}[/bold cyan]")

        # Shared HTTP
        self.groq_http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.GROQ_TIMEOUT),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            verify=False
        )
        self.embed_http = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.EMBED_TIMEOUT, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            verify=False
        )

    async def close(self) -> None:
        if self.neo4j:
            await self.neo4j.close()
        if self.arxiv_neo4j:
            await self.arxiv_neo4j.close()
        if self.async_supabase:
            try:
                await self.async_supabase.auth.sign_out()
            except Exception as e:
                log.debug(f"Supabase StoreA sign_out failed: {e}")
        if self.arxiv_async_supabase:
            try:
                await self.arxiv_async_supabase.auth.sign_out()
            except Exception as e:
                log.debug(f"Supabase StoreB sign_out failed: {e}")
        if self.groq_http:
            await self.groq_http.aclose()
        if self.embed_http:
            await self.embed_http.aclose()
        log.info("DualPool closed")

# Global instances
pool = DualPool()
