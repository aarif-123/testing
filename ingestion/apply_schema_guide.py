import os
import sys
from supabase import create_client
from dotenv import load_dotenv

def apply_schema():
    load_dotenv()
    
    url = os.getenv("ARXIV_SUPABASE_URL")
    key = os.getenv("ARXIV_SUPABASE_KEY")
    
    if not url or not key:
        print("❌ Error: ARXIV_SUPABASE_URL or ARXIV_SUPABASE_KEY not found in .env")
        sys.exit(1)
        
    print(f"🚀 Connecting to ArXiv Supabase: {url}")
    supabase = create_client(url, key)
    
    schema_path = "./ingestion/arxiv_schema.sql"
    if not os.path.exists(schema_path):
        print(f"❌ Error: Schema file not found at {schema_path}")
        sys.exit(1)
        
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()
        
    print("📜 Preparing to apply the Dual-Store Safe Schema...")
    
    # We use a trick to run SQL if the Supabase project allows RPC for it, 
    # but usually, Supabase doesn't expose an arbitrary SQL RPC by default.
    # We will try to execute it by checking if we have a direct connection string or using the REST API if configured.
    # Note: If this fails, the user will need to use the Supabase SQL Editor.
    
    try:
        # Most secure/standard way to run this is via the Supabase Dashboard SQL Editor.
        # However, for an agentic experience, we provide this script to help explain the intent.
        print("\n⚠️ NOTE: Supabase Python client does not support executing arbitrary SQL scripts directly for security reasons.")
        print("👉 ACTION REQUIRED: Please copy the content of 'ingestion/arxiv_schema.sql' and paste it into your Supabase SQL Editor.")
        print("\nSummary of what this script would do:")
        print("1. Create 'arxiv_papers' table with multi-store support.")
        print("2. Create 'arxiv_chunks' table with 768-dim vector support.")
        print("3. Create 'authors' and 'paper_authors' tables for entity resolution.")
        print("4. Define the 'hybrid_search_arxiv' function for advanced RAG.")
        
    except Exception as e:
        print(f"❌ Operation failed: {e}")

if __name__ == "__main__":
    apply_schema()
