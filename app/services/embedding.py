import asyncio
import httpx
from typing import List
import torch
from sentence_transformers import SentenceTransformer
from ..core.config import settings
from ..core.logging_config import log
from ..core.exceptions import EmbeddingError
from ..utils.cache import get_cache, set_cache, cache_key

# Global model container (lazily loaded)
_embed_model = None

async def preload_model():
    """Preload the embedding model at startup (Async)."""
    await get_local_model()

async def get_local_model():
    """Lazily load the SentenceTransformer model (Async)."""
    global _embed_model
    if _embed_model is None:
        if not settings.EMBED_LOCAL:
            log.error("Local embedding is required but disabled via config.")
            raise EmbeddingError("Local embedding is disabled via configuration.")
            
        def _load():
            try:
                # Detect device: cuda > mps > cpu
                device = "cpu"
                if torch.cuda.is_available():
                    device = "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    device = "mps"
                    
                log.info(f"Loading embedding model: {settings.EMBED_MODEL} on device: {device}")
                return SentenceTransformer(settings.EMBED_MODEL, device=device)
            except ImportError:
                log.warning("sentence-transformers or torch not installed; local embedding disabled.")
                return None
            except Exception as e:
                log.error(f"Failed to load local embedding model: {e}")
                return None
        
        _embed_model = await asyncio.to_thread(_load)
    return _embed_model

async def create_embedding(text: str) -> List[float]:
    """Generate normalized embedding for text via local model or HF API fallback."""
    ck = cache_key(text)
    cached = await get_cache("embed", ck)
    if cached:
        return cached

    model = await get_local_model()
    if not model:
        raise EmbeddingError("Local embedding model is not loaded. 'EMBED_LOCAL' is True but loading failed.")

    try:
        emb = await asyncio.to_thread(
            model.encode, text, normalize_embeddings=True
        )
        result = emb.tolist()
        await set_cache("embed", ck, result)
        return result
    except Exception as exc:
        raise EmbeddingError(f"Local embedding failed: {exc}")
