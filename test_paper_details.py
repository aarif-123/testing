import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

async def main():
    from app.services.arxiv_mcp import arxiv_mcp
    
    session = await arxiv_mcp._get_session()
    res = await session.call_tool("get_paper_details", arguments={"arxiv_id": "2306.04338v1"})
    
    with open("mcp_details_output.txt", "w") as f:
        f.write(repr(res))
    
    await arxiv_mcp.close()

asyncio.run(main())
