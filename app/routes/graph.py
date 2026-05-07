from fastapi import APIRouter, Request, HTTPException, Depends
from ..core.auth import verify_api_key
from ..utils.ratelimit import check_rate_limit
from ..services.graph_service import (
    get_paper_full, 
    get_author_network, 
    get_citation_path, 
    get_trending_papers
)
from ..core.models import CitationPathRequest

router = APIRouter(prefix="/api/graph", tags=["Graph Intelligence"])

@router.get("/paper/{paper_id}", dependencies=[Depends(verify_api_key)])
async def get_paper(paper_id: str, request: Request):
    await check_rate_limit(request.client.host if request.client else "unknown")
    result = await get_paper_full(paper_id)
    if not result:
        raise HTTPException(404, f"Paper '{paper_id}' not found.")
    return result

@router.get("/author/{author_name}", dependencies=[Depends(verify_api_key)])
async def get_author(author_name: str, request: Request):
    await check_rate_limit(request.client.host if request.client else "unknown")
    result = await get_author_network(author_name)
    if not result:
        raise HTTPException(404, f"Author '{author_name}' not found.")
    return result

@router.post("/citation-path", dependencies=[Depends(verify_api_key)])
async def citation_path(req: CitationPathRequest, request: Request):
    await check_rate_limit(request.client.host if request.client else "unknown")
    return await get_citation_path(req.from_paper, req.to_paper)

@router.get("/trending", dependencies=[Depends(verify_api_key)])
async def trending(request: Request):
    await check_rate_limit(request.client.host if request.client else "unknown")
    return await get_trending_papers()
