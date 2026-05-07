import json
import asyncio
import httpx
from typing import List, Dict, Any, Optional, AsyncGenerator
from ..core.config import settings
from ..core.logging_config import log
from ..core.exceptions import LLMError
from ..utils.cache import get_cache, set_cache, cache_key
from .pool import pool

async def groq_chat(
    messages: List[Dict],
    model: str,
    temperature: float = 0.1,
    max_tokens: int = 1024,
    retries: int = 2,
    json_mode: bool = False,
) -> str:
    """Standard non-streaming ChatCompletion."""
    ck = None
    if temperature == 0.0:
        ck = cache_key(str(messages), model, max_tokens)
        cached = await get_cache("llm", ck)
        if cached:
            log.debug("LLM cache hit")
            return cached

    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_err = None
    for attempt in range(retries + 1):
        try:
            r = await pool.groq_http.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            if r.status_code == 429:
                wait = min(int(r.headers.get("Retry-After", 5)), 15)
                log.warning(f"Groq 429 - wait {wait}s")
                await asyncio.sleep(wait)
                continue
            if r.status_code in (500, 503):
                await asyncio.sleep(2**attempt)
                continue
            if r.status_code != 200:
                raise LLMError(f"Groq HTTP {r.status_code}: {r.text[:300]}")
            
            result = r.json()["choices"][0]["message"]["content"]
            if ck:
                await set_cache("llm", ck, result)
            return result
            
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_err = e
            await asyncio.sleep(1.5**attempt)
            
    raise LLMError(f"Groq failed after {retries + 1} attempts: {last_err}")

async def groq_chat_stream(
    messages: List[Dict],
    model: str,
    temperature: float = 0.1,
    max_tokens: int = 1024,
) -> AsyncGenerator[str, None]:
    """Streaming ChatCompletion generator — reuses the pool's persistent HTTP client."""
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    # Reuse the pool's persistent connection to avoid per-request TLS handshake overhead
    client = pool.groq_http
    if client is None or client.is_closed:
        # Fallback: create ephemeral client if pool not ready
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0),
            verify=False,
        )
        _ephemeral = True
    else:
        _ephemeral = False

    try:
        async with client.stream(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=httpx.Timeout(60.0, connect=5.0),
        ) as r:
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 5))
                await asyncio.sleep(min(wait, 10))
                raise LLMError(f"Groq rate-limited (429). Retry after {wait}s.")
            if r.status_code != 200:
                raise LLMError(f"Groq Stream HTTP {r.status_code}")

            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except Exception:
                    continue
    finally:
        if _ephemeral and not client.is_closed:
            await client.aclose()
