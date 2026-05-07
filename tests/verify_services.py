
import os
import sys
import time
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load env 
load_dotenv(".env.local", override=True)
load_dotenv(".env", override=False)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

def header(text):
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)

def status(ok, label, detail=""):
    icon = "[OK]" if ok else "[FAIL]"
    print(f"  {icon} {label} - {detail}")

results = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "supabase": {"status": "UNTESTED", "details": {}},
    "neo4j": {"status": "UNTESTED", "details": {}},
}

def test_supabase():
    header("Testing Supabase")
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        status(True, "Supabase Client", "Created")
        
        # Test query
        resp = client.table("paper_chunks").select("id").limit(1).execute()
        status(True, "Query paper_chunks", f"Success, {len(resp.data)} rows")
        results["supabase"]["status"] = "OK"
    except Exception as e:
        status(False, "Supabase", str(e))
        results["supabase"]["status"] = "ERROR"

def test_neo4j():
    header("Testing Neo4j")
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        status(True, "Neo4j Connectivity", "Verified")
        
        with driver.session() as session:
            res = session.run("RETURN 1 as ping").single()
            status(True, "Neo4j Ping", "Success")
            
            node_count = session.run("MATCH (n) RETURN count(n) as count").single()["count"]
            status(True, "Node Count", f"{node_count}")
            
        driver.close()
        results["neo4j"]["status"] = "OK"
    except Exception as e:
        status(False, "Neo4j", str(e))
        results["neo4j"]["status"] = "ERROR"

if __name__ == "__main__":
    test_supabase()
    test_neo4j()
    
    with open("connectivity_report.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nReport saved to connectivity_report.json")
