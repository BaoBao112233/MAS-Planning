from typing import Optional, List
from typing import Any
from pydantic import BaseModel, Field

class PlanOption(BaseModel):
    id: int = Field(..., description="Plan option ID (1, 2, or 3)")
    name: str = Field(..., description="Plan name")
    focus: str = Field(..., description="Plan focus description")
    tasks: List[str] = Field(..., description="List of tasks in this plan")

class PlanOptionsResponse(BaseModel):
    type: str = Field("plan_options", description="Response type")
    message: str = Field(..., description="Instructions for user")
    options: List[PlanOption] = Field(..., description="Available plan options")
    sessionId: str = Field(..., description="Session ID")

class PlanSelectionRequest(BaseModel):
    sessionId: str = Field(..., description="Session ID")
    selectedPlanId: int = Field(..., description="Selected plan ID (1, 2, or 3)")

class ChatRequest(BaseModel):
    conversationId: str
    sessionId: str
    message: str

class ChatResponse(BaseModel):
    sessionId: str
    response: str
    error_status: str = "success"

# Request models
class ChatRequestAPI(BaseModel):
    conversationId: str = Field(..., description="Unique identifier for the conversation")
    sessionId: str = Field(..., description="Unique identifier for the user session")
    message: str = Field(..., description="User message to process")
    channelId: str = Field(..., description="Unique identifier for the channel")
    socialNetworkId: str = Field(..., description="Unique identifier for the social network")
    pageName: Optional[str] = Field(None, description="Name of the page (if applicable)")

# Response models
class APIResponse(BaseModel):
    response: str
    error_status: str = "success"



