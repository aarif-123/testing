from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from .core.config import settings, BASE_DIR
from .core.logging_config import log
from .services.pool import pool
from .routes import research, graph


from .utils.cache import init_redis, close_redis


import gc
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DualPool + Redis + Embedding Model
    log.info(f"Starting {settings.PROJECT_NAME} (v6.0 Modular)...")
    
    # Free RAM/VRAM before loading heavy models
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
        
    from .services.embedding import preload_model
    await preload_model()
    
    await init_redis()
    await pool.init()
    
    try:
        yield
        log.info("Lifespan yield finished naturally.")
    except asyncio.CancelledError:
        log.info("Lifespan cancelled (Shutdown/Reload).")
        pass
    finally:
        # Shutdown: Close connections
        log.info("Closing service connections...")
        
        # Check if the loop is still alive and running
        try:
            loop = asyncio.get_running_loop()
            if not loop.is_running():
                log.warning("Event loop is not running. Skipping async cleanup.")
                return
        except RuntimeError:
            log.warning("No running event loop found. Cleanup may be incomplete.")
            return

        # Perform cleanup with individual timeouts
        try:
            from .services.arxiv_mcp import arxiv_mcp
            await asyncio.wait_for(arxiv_mcp.close(), timeout=5.0)
        except Exception as e:
            log.debug(f"ArXivMCP cleanup error: {e}")

        try:
            await asyncio.wait_for(pool.close(), timeout=5.0)
        except Exception as e:
            log.debug(f"DualPool cleanup error: {e}")

        try:
            await asyncio.wait_for(close_redis(), timeout=3.0)
        except Exception as e:
            log.debug(f"Redis cleanup error: {e}")

        log.info("Shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="6.0.0",
    description="Production-grade GraphRAG Architecture",
    lifespan=lifespan,
)

# CORS Middleware
ALLOWED_ORIGINS = [
    o.strip()
    for o in settings.CORS_ORIGINS.split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-API-KEY"],
)

@app.get("/")
async def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app/")


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.exception(f"Unhandled ERROR: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error.",
            "error_type": type(exc).__name__
        }
    )


# Register Routers
app.include_router(research.router)
app.include_router(graph.router)


# Health Check
@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "ready": True,
        "service": settings.PROJECT_NAME
    }


@app.get("/api/health/full")
async def health_full():
    """Deep health check including dependencies."""
    import subprocess

    checks = {
        "api": "ok",
        "redis": "ok",
        "vector_store": "ok",
        "graph_store": "ok" if settings.NEO4J_ENABLED and pool.neo4j_ok else ("disabled" if not settings.NEO4J_ENABLED else "error"),
        "arxiv_mcp": "ok"
    }

    # Simple check for Docker/MCP
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
    except Exception:
        checks["arxiv_mcp"] = "error"

    # Status logic
    status = "healthy"
    if any(v == "error" for v in checks.values()):
        status = "degraded"

    return {
        "status": status,
        "checks": checks,
        "version": "6.0.0",
        "mcp_info": {
            "connected": checks["arxiv_mcp"] == "ok",
            "tool": "arxiv-mcp-docker"
        }
    }

# Frontend Static Files
_frontend_dir = BASE_DIR / "frontend"
if _frontend_dir.exists():
    app.mount("/app", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
    log.info(f"Frontend mounted at /app -> {_frontend_dir}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=(settings.ENV == "dev"),
        reload_dirs=["app"],
        reload_excludes=["*.log", "server_out.log", "server_error.log", "app.log"]
    )
