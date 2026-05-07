class GraphRAGError(Exception):
    """Base exception for the application."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.code = code

class EmbeddingError(GraphRAGError):
    """Raised when embedding generation fails."""
    def __init__(self, message: str):
        super().__init__(message, code="EMBEDDING_FAILURE")

class LLMError(GraphRAGError):
    """Raised when LLM call fails."""
    def __init__(self, message: str):
        super().__init__(message, code="LLM_FAILURE")

class GraphDatabaseError(GraphRAGError):
    """Raised when Neo4j operations fail."""
    def __init__(self, message: str):
        super().__init__(message, code="GRAPH_DB_FAILURE")

class VectorStoreError(GraphRAGError):
    """Raised when Supabase vector search fails."""
    def __init__(self, message: str):
        super().__init__(message, code="VECTOR_DB_FAILURE")
