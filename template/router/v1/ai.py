from typing import Optional, Union
import logging
import json
import os
import io
import tempfile
from datetime import datetime
from fastapi import APIRouter, Depends, BackgroundTasks, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from cachetools import TTLCache
from pydantic import Field
import requests
import httpx
import aiofiles
import traceback
from termcolor import colored

from template.agent.manager import ManagerAgent

# Session cache to store plan options for plan selection
session_cache = TTLCache(maxsize=1000, ttl=3600)  # 1 hour TTL
from template.agent.plan import PlanAgent
from template.agent.tool import ToolAgent
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
from template.utils.tts import text_to_speech_with_voice, speech_to_text
from template.utils.aws_transcribe_service import AWSTranscribeService

from gtts import gTTS
from pydub import AudioSegment
import speech_recognition as sr
from io import BytesIO

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

Router = APIRouter()

cache = TTLCache(maxsize=500, ttl=300)


@AiRouter.get("/voices")
async def get_available_voices():
    """
    Get all available voices from Google Cloud Text-to-Speech API.
    Returns a hierarchical structure: language_code -> model_type -> voices
    """
    try:
        logger.info(colored("🎤 Fetching available voices...", "cyan", attrs=["bold"]))
        
        from template.utils.tts import get_available_voices
        voices = get_available_voices()
        
        # Log summary
        total_languages = len(voices)
        total_voices = sum(len(model_voices) for lang in voices.values() for model_voices in lang.values())
        logger.info(colored(
            f"✅ Returning {total_voices} voices across {total_languages} languages",
            "green", attrs=["bold"]
        ))
        
        return {
            "success": True,
            "data": voices,
            "summary": {
                "total_languages": total_languages,
                "total_voices": total_voices
            }
        }
        
    except Exception as e:
        logger.error(colored(f"❌ Error fetching voices: {e}", "red", attrs=["bold"]))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch available voices: {str(e)}"
        )


@AiRouter.post("/chat/text", response_model=ChatResponse)
async def chat_text(request: ChatRequestAPI, background_tasks: BackgroundTasks):
    """Process a text chat message and return response with audio file"""
    try:
        # Lấy prompt từ file JSON nếu có chatId
        logger.info(f'⚙️  sessionId: {request.sessionId} | message: {request.message}')
        logger.info(f'🔑 Token received: {request.token[:10] if request.token else "None"}...')
        logger.info(f'🎤 Voice selected: {request.voice}')
        logger.info(f'🌍 Language code received: {request.language_code}')
        
        # Get language code from request, default to en-US if not provided
        language_code = request.language_code if request.language_code else "en-US"
        
        agent = ManagerAgent(
            temperature=0.2,
            model=env.MANAGER_MODEL_NAME,
            verbose=True,
            session_id=request.sessionId,
            conversation_id=request.conversationId,
            max_iteration=env.MAX_ITERATIONS,
            language_code=language_code  # Pass language code to agent
        )

        # Get voice from request, use default if not provided
        voice_name = request.voice if request.voice else "en-US-Neural2-A"
        logger.info(f'🎙️  Using voice: {voice_name} for language: {language_code}')

        # Check if this is a plan selection and retrieve cached plan options
        session_key = f"{request.sessionId}_{request.conversationId}"   
        cached_plans = session_cache.get(session_key)
        
        # Pass cached plans to the manager agent if available
        context = {}
        if cached_plans:
            context['cached_plan_options'] = cached_plans
        
        input_data = {
            "input": request.message,
        }

        logger.info(f'📤 Input data token: {request.token[:10]}...')

        env.OXII_API_KEY = request.token
        
         # Tool Agent handles all routing internally
        response = agent.invoke(input_data, context=context)

        # Store plan options in cache if response contains them
        if 'plan_options' in response:
            session_cache[session_key] = response['plan_options']
            logger.info(f"💾 Stored plan options for session {session_key}")

        # logger.info(f'📝 Response: {response}')
        
        response_text = response.get('output', 'Request processed successfully')
        
        # Generate audio file from response text
        try:
            # Save audio file temporarily
            audio_filename = f"response_{request.sessionId}_{request.conversationId}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
            temp_audio_path = f"/tmp/{audio_filename}"
            await text_to_speech_with_voice(response_text, temp_audio_path, voice_name, language_code)
            
            # Upload audio to S3 and get public URL
            logger.info(f"📤 Uploading audio to S3: {audio_filename}")
            s3_service = AWSTranscribeService()
            audio_url = s3_service.upload_to_s3(temp_audio_path)
            logger.info(f"✅ Audio uploaded to S3: {audio_url}")
            
            # Schedule cleanup of temporary file
            background_tasks.add_task(cleanup_temp_file, temp_audio_path, delay=60)  # 1 minute
            
            # Add audio file info to response
            response_with_audio = ChatResponse(
                sessionId=request.sessionId,
                response=response_text,
                audio_file_url=audio_url
            )
            
            return response_with_audio
            
        except Exception as e:
            logger.error(f"Error generating audio: {str(e)}", exc_info=True)
            # Return response without audio if TTS fails
            return ChatResponse(
                sessionId=request.sessionId,
                response=response_text,
                error_status="success" if response.get('success', True) else "error"
            )
        
    except Exception as e:
        error_msg = f"Error processing chat request: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return ChatResponse(
            sessionId=request.sessionId,
            response="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại.",
            error_status="error"
        )

@AiRouter.post("/chat/audio")
async def chat_audio(
    sessionId: str = Query(..., description="Unique identifier for the user session"),
    conversationId: str = Query(..., description="Unique identifier for the conversation"),
    token: str = Query(..., description="Authentication token"),
    voice: Optional[str] = Query("vi-VN-Neural2-A", description="Voice to use for text-to-speech (e.g., 'vi-VN-Neural2-A', 'en-US-Neural2-C')"),
    language_code: Optional[str] = Query("vi-VN", description="Language code for AI response (e.g., 'en-US', 'vi-VN')"),
    audio_file: UploadFile = File(..., description="Audio file to transcribe (wav, mp3, webm, ogg)"),
    background_tasks: BackgroundTasks = None
):
    """Process an audio chat message and return response with both text and audio"""
    try:
        logger.info(f'🎵 Audio chat - sessionId: {sessionId} | file: {audio_file.filename}')
        logger.info(f'🎙️  Using voice: {voice}')

        
        # Validate audio file
        if not audio_file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # Convert audio to text
        transcribed_text = await speech_to_text(audio_file)
        logger.info(f'📝 Transcribed text: {transcribed_text}')
        
        if not transcribed_text or not transcribed_text.strip():
            logger.warning(f"⚠️ Empty transcription for file: {audio_file.filename}")
            raise HTTPException(
                status_code=400, 
                detail="Could not transcribe audio. Please make sure the audio is clear and contains speech."
            )
        
        # Process the transcribed text through the chatbot
        agent = ManagerAgent(
            temperature=0.2,
            model=env.MANAGER_MODEL_NAME,
            verbose=True,
            session_id=sessionId,
            conversation_id=conversationId,
            language_code=language_code  # Pass language_code to agent
        )

        # Check if this is a plan selection and retrieve cached plan options
        session_key = f"{sessionId}_{conversationId}"   
        cached_plans = session_cache.get(session_key)
        
        # Pass cached plans to the manager agent if available
        context = {}
        if cached_plans:
            context['cached_plan_options'] = cached_plans
        
        input_data = {
            "message": transcribed_text,
        }

        env.OXII_API_KEY = token
        
        # Manager Agent handles all routing internally
        response = agent.invoke(input_data, context=context)

        # Store plan options in cache if response contains them
        if 'plan_options' in response:
            session_cache[session_key] = response['plan_options']
            logger.info(f"💾 Stored plan options for session {session_key}")

        # logger.info(f'📝 Response: {response}')
        
        response_text = response.get('output', 'Request processed successfully')
        
        # Generate audio file from response text
        audio_filename = f"response_{sessionId}_{conversationId}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        temp_audio_path = f"/tmp/{audio_filename}"
        
        # Use voice parameter with default language code
        voice_name = voice
        await text_to_speech_with_voice(response_text, temp_audio_path, voice_name, language_code)
        
        # Upload audio to S3 and get public URL
        logger.info(f"📤 Uploading audio to S3: {audio_filename}")
        s3_service = AWSTranscribeService()
        audio_url = s3_service.upload_to_s3(temp_audio_path)
        logger.info(f"✅ Audio uploaded to S3: {audio_url}")
        
        # Schedule cleanup of temporary file
        if background_tasks:
            background_tasks.add_task(cleanup_temp_file, temp_audio_path, delay=60)  # 1 minute
        
        return {
            "sessionId": sessionId,
            "transcribed_text": transcribed_text,
            "response": response_text,
            "error_status": "success" if response.get('success', True) else "error",
            "audio_file_url": audio_url
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing audio chat request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại."
        )

async def cleanup_temp_file(file_path: str, delay: int = 0):
    """Clean up temporary files after a delay"""
    import asyncio
    if delay > 0:
        await asyncio.sleep(delay)
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.info(f"🗑️ Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(colored(f"Error cleaning up file {file_path}: {str(e)}", "red", attrs=["bold"]))

@Router.get("/token", response_model=str)
async def get_token(
    user_phone: str,
    user_password: str,
    user_country: str = "VI"
):
    """
    Retrieve the authentication token from OXII API
    """

    BASE_URL = env.OXII_ROOT_API_URL
    url = f"{BASE_URL}/api/app/user/signin"

    payload = json.dumps({
        "phone": user_phone,
        "password": user_password,
        "country": user_country
    })
    headers = {
        'Content-Type': 'application/json',
        'X-Origin': 'smarthiz'
    }

    response = requests.request("POST", url, headers=headers, data=payload).json()
    if response['code'] == 200:
        return response['data']['token']
    else:
        return None