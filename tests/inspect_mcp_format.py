
import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def inspect_arxiv_details():
    server_params = StdioServerParameters(
        command="docker",
        args=["run", "-i", "--rm", "ghcr.io/tejas242/arxiv-mcp:latest"]
    )
    
    arxiv_id = "2510.25518" # Found from previous run
    print(f"--- Inspecting ArXiv Details for {arxiv_id} ---")
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                print(f"Calling 'get_paper_details' for {arxiv_id}...")
                details_result = await session.call_tool(
                    "get_paper_details",
                    arguments={"arxiv_id": arxiv_id}
                )
                
                print("\nRaw Details Output:")
                for detail_item in details_result.content:
                    if hasattr(detail_item, 'text'):
                        print(detail_item.text)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_arxiv_details())
