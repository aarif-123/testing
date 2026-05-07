from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator
from dataclasses import dataclass, field

class ChatMessage(BaseModel):
    role: str
    content: str

class ConversationRequest(BaseModel):
    messages: Optional[List[ChatMessage]] = Field(None)
    query: Optional[str] = Field(None, max_length=2000)
    text: Optional[str] = Field(None, max_length=2000)
    
    top_k: int = Field(8, ge=1, le=30)
    min_similarity: float = Field(0.25, ge=0.0, le=1.0)
    use_heavy: bool = False
    verify: bool = True
    filters: Optional[Dict[str, Any]] = None
    last_paper_context: Optional[str] = None
    session_id: Optional[str] = None

    @model_validator(mode='after')
    def validate_content(self) -> 'ConversationRequest':
        if not self.messages and not self.query and not self.text:
            raise ValueError("Must provide either 'messages', 'query', or 'text'")
        
        # If query is missing but messages exist, fill query from last user message
        if not self.query and self.messages:
            for m in reversed(self.messages):
                if m.role == 'user':
                    self.query = m.content
                    break
        
        # If messages is missing but query exists, initialize messages
        if not self.messages and self.query:
            self.messages = [ChatMessage(role="user", content=self.query)]
            
        return self

class BulkRequest(BaseModel):
    queries: List[str] = Field(..., min_length=1, max_length=10)
    top_k: int = Field(8, ge=1, le=20)

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[Dict[str, str]] = Field(..., min_length=1)
    temperature: float = Field(0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(800, ge=1, le=4096)
    stream: bool = False

class CompareRequest(BaseModel):
    paper_a: str = Field(..., description="Title or ID of first paper")
    paper_b: str = Field(..., description="Title or ID of second paper")
    aspects: Optional[List[str]] = Field(
        None, description="Specific aspects to compare"
    )

class TimelineRequest(BaseModel):
    topic: str = Field(..., max_length=500)
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    top_k: int = Field(10, ge=1, le=30)

class SurveyRequest(BaseModel):
    topic: str = Field(..., max_length=500)
    top_k: int = Field(15, ge=5, le=30)
    use_heavy: bool = True

class CitationPathRequest(BaseModel):
    from_paper: str
    to_paper: str

class ArXivSearchRequest(BaseModel):
    query: str = Field(..., max_length=500)
    max_results: int = Field(5, ge=1, le=20)

@dataclass
class QueryPlan:
    standalone_query: str
    route: str
    graph_anchors: List[str] = field(default_factory=list)
    vector_keywords: List[str] = field(default_factory=list)
    required_metrics: List[str] = field(default_factory=list)
    reasoning_path: str = ""
    intent: str = ""
    domain: str = ""
    ambiguous: bool = False
    cache_key_str: str = ""
    advanced_query_params: Dict[str, Any] = field(default_factory=dict)
    raw: Dict = field(default_factory=dict)
