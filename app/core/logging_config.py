import os
import logging
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
from .config import settings, BASE_DIR

def setup_logging():
    # Disable noisy logs
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.ERROR)

    # Setup Rich Logging
    console = Console()
    _log_handlers = [RichHandler(console=console, rich_tracebacks=True, markup=True)]

    if not os.getenv("VERCEL"):
        log_dir = BASE_DIR / ".logs"
        log_dir.mkdir(exist_ok=True)
        _log_handlers.append(
            logging.FileHandler(log_dir / "app.log", encoding="utf-8")
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=_log_handlers,
    )
    
    return logging.getLogger("graphrag")

log = setup_logging()
