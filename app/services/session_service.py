"""
Session Service — Manages server-side research sessions.
Papers uploaded or retrieved during a session are stored
in Redis and automatically cleaned up via TTL when the session ends.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from ..core.logging_config import log
from ..core.config import settings
from ..utils import cache


def _new_session_id() -> str:
    """Generate a unique session identifier."""
    return f"sess_{uuid.uuid4().hex[:12]}"


def _get_list_key(session_id: str) -> str:
    """Generate the Redis key for a session's paper list."""
    return f"{settings.PROJECT_NAME}:session_meta:{session_id}:papers"


class SessionService:
    """Server-side session lifecycle management."""

    async def create_session(self) -> Dict[str, Any]:
        """Create a new research session."""
        session_id = _new_session_id()
        log.info(f"Session created: {session_id}")
        return {
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }

    async def store_paper(
        self,
        session_id: str,
        filename: str,
        extracted_text: str,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Store an extracted paper in Redis for the current session.
        """
        paper_id = str(uuid.uuid4())
        record = {
            "id": paper_id,
            "session_id": session_id,
            "filename": filename,
            "extracted_text": extracted_text[:100000],  # Cap size for Redis
            "paper_metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Store full paper data using standard cache utility (24h TTL)
            paper_data_key = f"{session_id}:{paper_id}"
            await cache.set_cache("session_papers", paper_data_key, record, ttl=86400)
            
            # Update the session's list of papers
            if cache.redis_client:
                full_list_key = _get_list_key(session_id)
                await cache.redis_client.rpush(full_list_key, paper_id)
                await cache.redis_client.expire(full_list_key, 86400)
            else:
                # In-memory fallback for paper list
                list_key = _get_list_key(session_id)
                if list_key not in cache.MEM_CACHE:
                    cache.MEM_CACHE[list_key] = []
                if paper_id not in cache.MEM_CACHE[list_key]:
                    cache.MEM_CACHE[list_key].append(paper_id)
            
            log.info(f"Stored paper {filename} in session {session_id} (Redis: {bool(cache.redis_client)})")
            return {
                "id": paper_id,
                "session_id": session_id,
                "filename": filename,
                "stored": True,
                "text_length": len(extracted_text),
                "method": "redis_ephemeral" if cache.redis_client else "memory_ephemeral"
            }
        except Exception as e:
            log.error(f"Failed to store paper: {e}")
            return {
                "id": paper_id,
                "session_id": session_id,
                "filename": filename,
                "stored": False,
                "reason": str(e),
            }

    async def get_session_papers(self, session_id: str) -> List[Dict]:
        """Retrieve all papers for a session."""
        try:
            paper_ids = []
            if cache.redis_client:
                full_list_key = _get_list_key(session_id)
                paper_ids = await cache.redis_client.lrange(full_list_key, 0, -1)
            else:
                # In-memory fallback
                list_key = _get_list_key(session_id)
                paper_ids = cache.MEM_CACHE.get(list_key, [])
            
            papers = []
            for pid in paper_ids:
                data = await cache.get_cache("session_papers", f"{session_id}:{pid}")
                if data:
                    # Strip heavy text for listing purposes
                    papers.append({
                        "id": data["id"],
                        "session_id": session_id,
                        "filename": data["filename"],
                        "paper_metadata": data["paper_metadata"],
                        "created_at": data["created_at"]
                    })
            return papers
        except Exception as e:
            log.error(f"Failed to get session papers: {e}")
            return []

    async def get_session_context(self, session_id: str) -> str:
        """
        Get combined text from all session papers in Redis.
        """
        try:
            papers = await self.get_session_papers(session_id)
            if not papers:
                return ""

            parts = []
            for p in papers:
                # Fetch full data including text
                data = await cache.get_cache("session_papers", f"{session_id}:{p['id']}")
                if data:
                    fname = data.get("filename", "unknown")
                    text = data.get("extracted_text", "")
                    parts.append(
                        f"=== UPLOADED: {fname} ===\n"
                        f"{text[:10000]}"  # Generous context allowed in Redis flow
                    )
            return "\n\n".join(parts)
        except Exception as e:
            log.error(f"Failed to get session context from Redis: {e}")
            return ""

    async def end_session(self, session_id: str) -> Dict[str, Any]:
        """
        End a session — delete association in Redis immediately.
        """
        try:
            if not cache.redis_client:
                return {"session_id": session_id, "cleaned": False}
                
            full_list_key = _get_list_key(session_id)
            paper_ids = await cache.redis_client.lrange(full_list_key, 0, -1)
            
            # Delete individual paper records
            for pid in paper_ids:
                key = f"{settings.PROJECT_NAME}:session_papers:{session_id}:{pid}"
                await cache.redis_client.delete(key)
            
            # Delete the list itself
            await cache.redis_client.delete(full_list_key)
            
            log.info(f"Session {session_id} ended and Redis keys actively cleaned.")
            return {
                "session_id": session_id,
                "cleaned": True,
                "papers_removed": len(paper_ids),
            }
        except Exception as e:
            log.error(f"Session cleanup failed in Redis: {e}")
            return {
                "session_id": session_id,
                "cleaned": False,
                "error": str(e),
            }

    async def cleanup_stale_sessions(self, max_age_hours: int = 24):
        """
        Redis automatically handles TTL expirations, so explicit 
        background cleanup is no longer required. Kept for interface compatibility.
        """
        pass


# Global singleton
session_service = SessionService()
