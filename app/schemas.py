from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12_000)
    stream: bool = False


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    answer: str
    model: str
    usage: TokenUsage


class UsageSummary(BaseModel):
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class UsageEvent(BaseModel):
    created_at: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class UsageResponse(BaseModel):
    summary: UsageSummary
    recent: list[UsageEvent]


class Citation(BaseModel):
    document: str
    page: int
    heading: str | None = None
    snippet: str | None = None


class RetrievedChunk(BaseModel):
    document: str
    page: int
    heading: str | None = None
    content: str
    score: float


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12_000)
    top_k: int = Field(default=4, ge=1, le=20)


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[Citation]
    model: str
    usage: TokenUsage
    context: list[RetrievedChunk] = Field(default_factory=list)
