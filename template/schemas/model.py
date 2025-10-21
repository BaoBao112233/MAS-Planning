from typing import Optional
from typing import Any
from pydantic import BaseModel, Field

class ResponseFormatter(BaseModel):
    message: str = Field(..., description="The response message from the chatbot")
    code: str = Field("General", description="The category code of the response, e.g., CSKH, SAL, General")
    notifi: str = Field("", description="Notification message related to the response")
    voc_id: str = Field("", description="VOC identifier, if applicable")
    status: str = Field("error", description="Status of the response, e.g., success or error")

class ChatRequest(BaseModel):
    conversationId: str
    sessionId: str
    message: str
    channelId: str
    socialNetworkId: str
    pageName: Optional[str] = None

class ChatResponse(BaseModel):
    sessionId: str
    response: ResponseFormatter
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



