import logging
import json
import os
from datetime import datetime
from fastapi import APIRouter, Depends, BackgroundTasks
from cachetools import TTLCache

from template.agent.plan import PlanAgent
from template.configs.environments import env
from template.schemas.model import (
    ChatRequest, 
    ChatResponse, 
    ChatRequestAPI,
    ResponseFormatter,
    APIResponse
)
from template.agent.prompts import CLASSIFICATION_PROMPT, DEFAULT_CLASSIFICATION_PROMPT, SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

AiRouter = APIRouter(
    prefix="/ai", tags=["Chat AI"]
)

Prompt_Router = APIRouter(
    prefix="/prompt", tags=["Prompt Management"]
)

cache = TTLCache(maxsize=500, ttl=300)


@AiRouter.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequestAPI, background_tasks: BackgroundTasks):
    """Process a chat message and return a response"""
    try:
        # Lấy prompt từ file JSON nếu có chatId
        logger.info(f'⚙️  sessionId: {request.sessionId} | channelId: {request.channelId} | socialNetworkId: {request.socialNetworkId} | message: {request.message} | pageName: {request.pageName}')
        agent = PlanAgent(
            temperature=0.2,
            model=env.MODEL_NAME
        )
        # Process the request
        chat_request = request.message
        response = agent.invoke(chat_request)
        
        return response
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        return ChatResponse(
            sessionId=request.sessionId,
            response=ResponseFormatter(
                message="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại.",
                code="General",
                notifi="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại.",
                voc_id="",
                status="error"
            ),
            error_status="error"
        )