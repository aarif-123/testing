import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory: testing/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env.local", override=True)
load_dotenv(BASE_DIR / ".env", override=False)

class Settings:
    # API & Environment
    PROJECT_NAME: str = "Aether GraphRAG Assistant"
    PORT: int = int(os.getenv("PORT", "8000"))
    ENV: str = os.getenv("ENV", "dev")
    APP_API_KEY: str = os.getenv("APP_API_KEY", "dev-key-12345")
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    
    # Store A (DBLP)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    NEO4J_URI: str = os.getenv("NEO4J_URI")
    NEO4J_USER: str = os.getenv("NEO4J_USER")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD")
    
    # Store B (ArXiv)
    ARXIV_SUPABASE_URL: str = os.getenv("ARXIV_SUPABASE_URL", "")
    ARXIV_SUPABASE_KEY: str = os.getenv("ARXIV_SUPABASE_KEY", "")
    ARXIV_NEO4J_URI: str = os.getenv("ARXIV_NEO4J_URI", "")
    ARXIV_NEO4J_USER: str = os.getenv("ARXIV_NEO4J_USER", "neo4j")
    ARXIV_NEO4J_PASSWORD: str = os.getenv("ARXIV_NEO4J_PASSWORD", "")
    STORE_B_ENABLED: bool = bool(os.getenv("ARXIV_SUPABASE_URL", "") and os.getenv("ARXIV_SUPABASE_KEY", ""))

    # AI models
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")
    HF_TOKEN: str = os.getenv("HF_TOKEN")
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "BAAI/bge-base-en")
    EMBED_LOCAL: bool = bool(os.getenv("EMBED_LOCAL", "True") == "True")
    REASON_MODEL: str = os.getenv(
        "REASON_MODEL", "llama-3.3-70b-versatile"
    )
    HEAVY_MODEL: str = os.getenv(
        "HEAVY_MODEL", "llama-3.3-70b-versatile"
    )
    PLAN_MODEL: str = os.getenv(
        "PLAN_MODEL", "llama-3.3-70b-versatile"
    )
    
    # RAG Tuning
    MAX_GRAPH_NODES: int = int(os.getenv("MAX_GRAPH_NODES", "25"))
    RELEVANCE_FLOOR: float = float(os.getenv("RELEVANCE_FLOOR", "0.22"))
    MMR_LAMBDA: float = float(os.getenv("MMR_LAMBDA", "0.6"))
    
    # Performance & Caching
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_ENABLED: bool = bool(os.getenv("CACHE_ENABLED", "True") == "True")
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "300"))
    CACHE_MAX: int = int(os.getenv("CACHE_MAX", "512"))
    RATE_LIMIT_PER_MIN: int = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "60"))
    GROQ_TIMEOUT: int = int(os.getenv("GROQ_TIMEOUT", "45"))
    EMBED_TIMEOUT: int = int(os.getenv("EMBED_TIMEOUT", "20"))

    def validate(self):
        """Simple check for required credentials."""
        required = [
            "SUPABASE_URL", "SUPABASE_KEY",
            "NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD",
            "GROQ_API_KEY"
        ]
        missing = [v for v in required if not getattr(self, v)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

settings = Settings()
settings.validate()
