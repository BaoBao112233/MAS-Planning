from typing import Union
import logging
import json
import os
from datetime import datetime
from fastapi import APIRouter, Depends, BackgroundTasks
from cachetools import TTLCache

from template.agent.plan import PlanAgent

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
        logger.info(f'⚙️  sessionId: {request.sessionId} | channelId: {request.channelId} | socialNetworkId: {request.socialNetworkId} | message: {request.message} | pageName: {request.pageName}')
        agent = PlanAgent(
            temperature=0.2,
            model=env.MODEL_NAME
        )

        await agent.init_async()

        # Process the request
        chat_request = request.message
        
        # Check if this is a plan selection (user replied with 1, 2, or 3 or Plan 1, etc.)
        if chat_request.strip() in ['1', '2', '3'] or any(x in chat_request.lower() for x in ['plan 1', 'plan 2', 'plan 3']):
            if chat_request.strip() in ['1', '2', '3']:
                selected_plan_id = int(chat_request.strip())
            else:
                # Extract plan number from "plan 1", "plan 2", etc.
                if 'plan 1' in chat_request.lower():
                    selected_plan_id = 1
                elif 'plan 2' in chat_request.lower():
                    selected_plan_id = 2
                elif 'plan 3' in chat_request.lower():
                    selected_plan_id = 3
                else:
                    selected_plan_id = 1  # default
            
            # Get cached plan options for this session
            session_key = f"{request.sessionId}_{request.conversationId}"
            cached_plans = session_cache.get(session_key)
            
            if cached_plans:
                # Create request with plan selection context and cached plan options
                response = agent.invoke(chat_request, selected_plan_id=selected_plan_id, plan_options=cached_plans)
            else:
                response = {"output": "❌ No previous plans found. Please create a new plan first."}
            
            return ChatResponse(
                sessionId=request.sessionId,
                response=response.get('output', 'Plan executed successfully'),
                error_status="success"
            )
        
        # Normal plan creation request
        response = agent.invoke(chat_request)

        logger.info(f'📝 Response: {response}')
        
        # Check if we need to return plan options
        if response.get('needs_user_selection', False):
            plan_options = response.get('plan_options', {})
            
            # Save plan options to cache for later selection
            session_key = f"{request.sessionId}_{request.conversationId}"
            session_cache[session_key] = plan_options
            
            # Format plan options as a nicely formatted message
            security_plan = plan_options.get('security_plan', [])
            convenience_plan = plan_options.get('convenience_plan', [])
            energy_plan = plan_options.get('energy_plan', [])
            
            formatted_message = "Please select your preferred plan:\n\n"
            
            # Plan A - Security Priority Plan
            formatted_message += "1. **Plan A: Security Priority Plan**\n\n"
            formatted_message += "    Goal: Maximum safety and security\n\n"
            formatted_message += "    Tasks:\n"
            for i, task in enumerate(security_plan, 1):
                formatted_message += f"    - {task}\n"
            formatted_message += "\n"
            
            # Plan B - Convenience Priority Plan  
            formatted_message += "2. **Plan B: Convenience Priority Plan**\n\n"
            formatted_message += "    Goal: User experience and ease of use\n\n"
            formatted_message += "    Tasks:\n"
            for i, task in enumerate(convenience_plan, 1):
                formatted_message += f"    - {task}\n"
            formatted_message += "\n"
            
            # Plan C - Energy Efficiency Priority Plan
            formatted_message += "3. **Plan C: Energy Efficiency Priority Plan**\n\n"
            formatted_message += "    Goal: Minimal resource consumption\n\n"
            formatted_message += "    Tasks:\n"
            for i, task in enumerate(energy_plan, 1):
                formatted_message += f"    - {task}\n"
            
            formatted_message += "\nPlease reply with the number (1, 2, or 3) of your preferred plan."
            
            return ChatResponse(
                sessionId=request.sessionId,
                response=formatted_message,
                error_status="success"
            )
        
        # Normal response
        return ChatResponse(
            sessionId=request.sessionId,
            response=response.get('output', 'Plan created successfully'),
            error_status="success"
        )
        
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        return ChatResponse(
            sessionId=request.sessionId,
            response="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại.",
            error_status="error"
        )

