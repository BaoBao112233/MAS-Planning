from typing import Union
import logging
import json
import os
from datetime import datetime
from fastapi import APIRouter, Depends, BackgroundTasks
from cachetools import TTLCache

from template.agent.manager import ManagerAgent

# Session cache to store plan options for plan selection
session_cache = TTLCache(maxsize=1000, ttl=3600)  # 1 hour TTL
from template.configs.environments import env
from template.schemas.model import (
    ChatRequest, 
    ChatResponse, 
    ChatRequestAPI,
    APIResponse,
    PlanOptionsResponse,
    PlanOption,
    PlanSelectionRequest
)
from template.agent.prompts import CLASSIFICATION_PROMPT, DEFAULT_CLASSIFICATION_PROMPT, SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',  # format thời gian
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
        logger.info(f'⚙️  sessionId: {request.sessionId} | message: {request.message}')
        agent = ManagerAgent(
            temperature=0.2,
            model=env.MODEL_NAME,
            verbose=True,
            session_id=request.sessionId,  # Pass session_id for chat history
            conversation_id=request.conversationId
        )

        # Check if this is a plan selection and retrieve cached plan options
        session_key = f"{request.sessionId}_{request.conversationId}"   
        cached_plans = session_cache.get(session_key)
        
        # Pass cached plans to the manager agent if available
        context = {}
        if cached_plans:
            context['cached_plan_options'] = cached_plans
        
        input_data = {
            "message": request.message,
            "token": request.token
        }
        
        # Manager Agent handles all routing internally
        response = agent.invoke(input_data, context=context)

        # Store plan options in cache if response contains them
        if 'plan_options' in response:
            session_cache[session_key] = response['plan_options']
            logger.info(f"💾 Stored plan options for session {session_key}")

        logger.info(f'📝 Response: {response}')
        
        # Manager Agent provides formatted response directly
        return ChatResponse(
            sessionId=request.sessionId,
            response=response.get('output', 'Request processed successfully'),
            error_status="success" if response.get('success', True) else "error"
        )
        
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        return ChatResponse(
            sessionId=request.sessionId,
            response="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại.",
            error_status="error"
        )

