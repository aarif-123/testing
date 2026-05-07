import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

async def main():
    from app.services.arxiv_mcp import arxiv_mcp
    
    session = await arxiv_mcp._get_session()
    tools = await session.list_tools()
    
    with open("mcp_tools_output.txt", "w") as f:
        f.write(repr(tools))
    
    await arxiv_mcp.close()

asyncio.run(main())
