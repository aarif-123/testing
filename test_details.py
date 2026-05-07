import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

async def main():
    from app.services.arxiv_mcp import arxiv_mcp
    
    res = await arxiv_mcp.get_details("2306.04338v1")
    print("get_details res:", repr(res))
    
    await arxiv_mcp.close()

asyncio.run(main())
