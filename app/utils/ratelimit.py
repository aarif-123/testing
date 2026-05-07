import time
from typing import Dict, List
from fastapi import HTTPException
from ..core.config import settings

_rate_store: Dict[str, List[float]] = {}
_last_cleanup = time.time()

async def check_rate_limit(client_ip: str) -> None:
    global _last_cleanup, _rate_store
    now = time.time()
    
    # Cleanup every 5 minutes
    if now - _last_cleanup > 300:
        cutoff = now - 60
        _rate_store = {
            k: [t for t in v if t > cutoff]
            for k, v in _rate_store.items()
            if any(t > cutoff for t in v)
        }
        _last_cleanup = now
        
    hits = [t for t in _rate_store.get(client_ip, []) if now - t < 60.0]
    if len(hits) >= settings.RATE_LIMIT_PER_MIN:
        raise HTTPException(429, f"Rate limit: max {settings.RATE_LIMIT_PER_MIN}/min.")
        
    hits.append(now)
    _rate_store[client_ip] = hits
