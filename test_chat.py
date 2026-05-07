import asyncio
import httpx
import json

async def test_chat():
    req = {
        "messages": [
            {"role": "user", "content": "Find me papers on graphrag"}
        ],
        "top_k": 3,
        "min_similarity": 0.1,
        "use_heavy": False,
        "verify": True
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", "http://127.0.0.1:8000/api/chat", json=req, headers={"Authorization": "Bearer dev_aether_key_2025"}) as response:
            print(f"Status: {response.status_code}")
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("type") == "metadata":
                        print("METADATA RECEIVED:")
                        papers = data.get("source_nodes", {}).get("papers", [])
                        for p in papers:
                            print(f"- Title: {p.get('title')}")
                            print(f"  URL: {p.get('url')}")
                            print(f"  Abstract: {p.get('abstract')}")

if __name__ == "__main__":
    asyncio.run(test_chat())
