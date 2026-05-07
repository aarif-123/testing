import asyncio
from typing import List, Dict, Any
from ..core.logging_config import log
from ..core.config import settings
from .pool import pool


class UserGraphService:
    """
    Manages the personalized Knowledge Graph for Users traversing queries and topics.
    Designed for memory, context retrieval, and personalized weighting.

    Uses the async Neo4j driver (pool.arxiv_neo4j) directly to avoid blocking
    the event loop with asyncio.to_thread.
    """

    async def _run_query(self, query: str, parameters: Dict[str, Any] = None) -> List[Dict]:
        """Helper to safely execute Cypher over the Neo4j Store B async driver."""
        if not pool.arxiv_neo4j_ok or pool.arxiv_neo4j is None:
            return []
        try:
            async with pool.arxiv_neo4j.session() as session:
                result = await session.run(query, parameters or {})
                return [dict(record) for record in await result.data()]
        except Exception as e:
            log.warning(f"UserGraph query failed: {e}")
            return []

    async def get_user_context(self, user_id: str, limit: int = 5) -> List[Dict]:
        """
        Retrieves the top interests for a user dynamically based on decayed weights.
        """
        query = """
        MATCH (u:User {id: $user_id})-[r:INTERESTED_IN]->(t:Topic)
        RETURN t.name AS topic, r.weight AS weight, r.last_updated AS updated
        ORDER BY r.weight DESC
        LIMIT $limit
        """
        return await self._run_query(query, {"user_id": user_id, "limit": limit})

    async def update_user_interests(self, user_id: str, query_text: str, topics: List[str]):
        """
        Updates the interest graph asynchronously when a user completes a query.
        Also creates the session and query nodes.
        """
        cypher = """
        // 1. Ensure User
        MERGE (u:User {id: $user_id})

        // 2. Log Query
        CREATE (q:Query {text: $query_text, timestamp: timestamp()})
        MERGE (u)-[:ASKED]->(q)

        // 3. Update or Create Topics with Interest Weight
        WITH u, q
        UNWIND $topics AS topic_name
        MERGE (t:Topic {name: toLower(topic_name)})
        MERGE (q)-[:EXPLORES]->(t)

        // 4. Update Interest Weight Dynamically & Upsert Last Timestamp
        MERGE (u)-[r:INTERESTED_IN]->(t)
        ON CREATE SET r.weight = 1.0, r.last_updated = timestamp()
        ON MATCH SET r.weight = r.weight + 0.5, r.last_updated = timestamp()
        """
        params = {
            "user_id": user_id,
            "query_text": query_text,
            "topics": topics
        }
        await self._run_query(cypher, params)
        log.info(f"UserGraph updated: User {user_id} engaged with {len(topics)} topics.")

    async def trigger_time_decay(self):
        """
        CRON Job endpoint: Exponential decay for historical context over time.
        Any interest not accessed recently fades smoothly.
        """
        cypher = """
        MATCH ()-[r:INTERESTED_IN]->()
        // Decay by 5% every run
        SET r.weight = r.weight * 0.95
        """
        await self._run_query(cypher)
        log.info("UserGraph time-decay triggered successfully.")


user_graph = UserGraphService()
