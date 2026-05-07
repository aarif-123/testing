import json
import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from app.mcp_service import ArXivMCPService

def test_parser():
    service = ArXivMCPService()
    
    mock_raw_output = """
**Retrieval Augmented Generation (RAG) for Fintech: Agentic Design and Evaluation**

**Authors:** Thomas Cook, Richard Osuagwu, Liman Tsatiashvili et al. (7 total authors)
**arXiv ID:** 2510.25518v1
**Published:** 2025-10-29
**Primary Category:** cs.AI

**Abstract:**
Retrieval-Augmented Generation (RAG) systems often face limitations in specialized domains such as fintech, where domain-specific ontologies, dense terminology, and acronyms complicate effective retrieval and synthesis. This paper introduces an agentic RAG architecture...

**Links:**
- Abstract: https://arxiv.org/abs/2510.25518v1
- PDF: https://arxiv.org/pdf/2510.25518v1
    """
    
    parsed = service.format_for_db(mock_raw_output)
    
    print("--- Parsed Result ---")
    print(json.dumps(parsed, indent=2))
    
    # Simple assertions
    assert parsed["title"] == "Retrieval Augmented Generation (RAG) for Fintech: Agentic Design and Evaluation"
    assert parsed["arxiv_id"] == "2510.25518v1"
    assert "Thomas Cook" in parsed["authors"]
    assert parsed["year"] == 2025
    assert len(parsed["abstract"]) > 50
    assert parsed["id"] is not None
    
    print("\n✅ Parser test passed!")

if __name__ == "__main__":
    test_parser()
