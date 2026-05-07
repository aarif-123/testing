
import sys
import os

try:
    import fastapi
    print("fastapi ok")
except ImportError:
    print("fastapi missing")

try:
    import mcp
    print("mcp ok")
except ImportError:
    print("mcp missing")

try:
    from app import mcp_service
    print("mcp_service ok")
except ImportError as e:
    print(f"mcp_service import failed: {e}")
except Exception as e:
    print(f"mcp_service error: {e}")

try:
    from app import app
    print("app import ok")
except ImportError as e:
    print(f"app import failed: {e}")
except Exception as e:
    print(f"app error: {e}")
