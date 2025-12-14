from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import uuid

class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0
    frequency_penalty: Optional[float] = 0
    logit_bias: Optional[Dict[str, float]] = None
    user: Optional[str] = None

class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None

class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Optional[ChatCompletionUsage] = None

class Job(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_model_id: str
    resolved_model_id: str
    provider_id: Optional[str] = None
    route_name: Optional[str] = None
    request: ChatCompletionRequest
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    status: str = "pending" # pending, running, completed, diff_provider_requeued
    error: Optional[str] = None
    normalized_error: Optional[str] = None # For fallback
    response: Optional[ChatCompletionResponse] = None
    attempts: List[Dict[str, Any]] = [] # Track fallback attempts

    class Config:
        arbitrary_types_allowed = True
