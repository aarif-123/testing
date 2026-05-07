from fastapi import Security, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings

security = HTTPBearer(auto_error=False)

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Verify the Bearer token against the configured APP_API_KEY.
    Bypassed if settings.ENV is 'dev'.
    """
    if settings.ENV == "dev":
        return "dev-bypass"

    if not credentials or credentials.credentials != settings.APP_API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Invalid or missing API Key"
        )
    return credentials.credentials
