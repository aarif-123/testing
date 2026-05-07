"""
GraphRAG Research Assistant v6.0 (Modular Edition)
Redirector to the new main application container.
"""

from .main import app

if __name__ == "__main__":
    import uvicorn
    from .core.config import settings
    uvicorn.run(
        "app.app:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=(settings.ENV == "dev")
    )
