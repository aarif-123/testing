import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# -----------------------------
# ✅ MCP SERVER CONFIG
# -----------------------------
MCP_SERVER = StdioServerParameters(
    command="docker",
    args=[
        "run",
        "-i",
        "--rm",
        "-e", "ARXIV_STORAGE_PATH=/data",
        "-v", "C:\\Users\\Mohmmed Aarif\\Downloads\\arxivdestopdocker:/data",
        "mcp/arxiv-mcp-server"
    ]
)

# -----------------------------
# 🧠 SAFE EXTRACT (ULTRA ROBUST)
# -----------------------------
def safe_extract(result):
    try:
        raw = result.content[0]

        # Case 1: has text
        if hasattr(raw, "text"):
            text = raw.text.strip()

            # Try JSON
            try:
                return json.loads(text)
            except:
                return text

        return raw

    except Exception as e:
        print("❌ Extraction failed:", result.content)
        raise e


# -----------------------------
# 🔍 SEARCH PAPERS
# -----------------------------
async def search_papers(session):
    print("\n🔍 Searching papers...\n")

    result = await session.call_tool(
        "search_papers",
        {
            "query": '"transformer architecture" AND "attention"',
            "categories": ["cs.CL", "cs.AI"],
            "max_results": 3,
            "sort_by": "relevance"
        }
    )

    data = safe_extract(result)

    if not isinstance(data, dict):
        print("⚠️ Unexpected format:", data)
        return []

    papers = data.get("papers", [])

    if not papers:
        print("❌ No papers found")
        print("Raw:", data)
        return []

    normalized = []
    for p in papers:
        normalized.append({
            "arxiv_id": p.get("id"),
            "title": p.get("title"),
            "authors": p.get("authors", []),
            "abstract": p.get("abstract", ""),
            "categories": p.get("categories", []),
            "published": p.get("published"),
            "url": p.get("url")
        })

    for i, p in enumerate(normalized, 1):
        print(f"{i}. {p['title']} ({p['arxiv_id']})")

    return normalized


# -----------------------------
# 📥 DOWNLOAD (RETRY SAFE)
# -----------------------------
async def download_paper(session, paper_id):
    print(f"\n📥 Downloading paper: {paper_id}\n")

    try:
        await session.call_tool("download_paper", {
            "paper_id": paper_id
        })
        print("✅ Download triggered\n")
    except Exception as e:
        print("⚠️ Download failed:", e)


# -----------------------------
# 📖 READ WITH RETRY (CRITICAL)
# -----------------------------
async def read_with_retry(session, paper_id, retries=6):
    print(f"\n📖 Reading paper: {paper_id}\n")

    for i in range(retries):
        try:
            result = await session.call_tool(
                "read_paper",
                {"paper_id": paper_id}
            )

            raw = result.content[0].text

            # If valid content
            if raw and "error" not in raw.lower():
                print("✅ Paper loaded successfully\n")
                print("🔹 Preview:\n")
                print(raw[:1000])
                return True

        except Exception as e:
            print("⚠️ Read error:", e)

        print(f"⏳ Retry reading... ({i+1}/{retries})")
        await asyncio.sleep(2)

    print("❌ Failed to read paper after retries\n")
    return False


# -----------------------------
# 🔧 TOOL EXTRACTION
# -----------------------------
def extract_tool_names(tools):
    names = []
    for t in tools:
        if isinstance(t, tuple):
            names.append(t[0])
        elif hasattr(t, "name"):
            names.append(t.name)
        else:
            names.append(str(t))
    return names


# -----------------------------
# 🔥 MAIN PIPELINE (FINAL)
# -----------------------------
async def main():
    async with stdio_client(MCP_SERVER) as (read, write):
        async with ClientSession(read, write) as session:

            print("🚀 Initializing MCP session...\n")
            await session.initialize()

            tools = await session.list_tools()
            print("🛠 Available tools:", extract_tool_names(tools), "\n")

            # 1️⃣ SEARCH
            papers = await search_papers(session)

            if not papers:
                return

            print("\n📦 Normalized Data:\n", papers)

            paper_id = papers[0]["arxiv_id"]

            # 2️⃣ DOWNLOAD
            await download_paper(session, paper_id)

            # 3️⃣ WAIT (IMPORTANT BUFFER)
            print("\n⏳ Waiting for processing...\n")
            await asyncio.sleep(5)

            # 4️⃣ READ (RETRY UNTIL READY)
            success = await read_with_retry(session, paper_id)

            if not success:
                print("⚠️ Paper may still be processing. Try again later.")


# -----------------------------
# ▶️ RUN
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())