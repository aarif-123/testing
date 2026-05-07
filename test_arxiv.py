import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

async def main():
    from app.services.arxiv_mcp import arxiv_mcp
    
    res = await arxiv_mcp.search_papers("machine learning", limit=2)
    print("mcp_res type:", type(res))
    print("mcp_res:", repr(res))
    
    temp_papers = []
    for raw in res:
        print("raw type:", type(raw))
        papers = arxiv_mcp.parse_multiple_papers(raw)
        print("parsed papers:", papers)
        temp_papers.extend(papers)
    
    await arxiv_mcp.close()

asyncio.run(main())
