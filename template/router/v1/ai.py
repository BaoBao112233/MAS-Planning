from typing import Union
import logging
import json
import os
import io
import tempfile
from datetime import datetime
from fastapi import APIRouter, Depends, BackgroundTasks, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from cachetools import TTLCache
import requests
import httpx
import aiofiles
import traceback
from langfuse import Langfuse
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

# Initialize Langfuse
langfuse = Langfuse(
    public_key=env.LANGFUSE_PUBLIC_KEY,
    secret_key=env.LANGFUSE_SECRET_KEY,
    host=env.LANGFUSE_HOST
)

# ElevenLabs configuration
ELEVENLABS_API_KEY = env.ELEVENLABS_API_KEY
ELEVENLABS_BASE_URL = env.ELEVENLABS_BASE_URL  
DEFAULT_VOICE_ID = env.ELEVENLABS_VOICE_ID

async def text_to_speech(text: str, path: str):
    # """Convert text to speech using ElevenLabs API"""
    # url = f"{env.ELEVENLABS_BASE_URL}/text-to-speech/{env.ELEVENLABS_VOICE_ID}"
    # headers = {
    #     "Accept": "audio/mpeg",
    #     "Content-Type": "application/json",
    #     "xi-api-key": env.ELEVENLABS_API_KEY
    # }
    # data = {
    #     "text": text,
    #     "model_id": env.ELEVENLABS_MODEL_ID,
    #     "voice_settings": {
    #         "stability": env.ELEVENLABS_STABILITY,
    #         "similarity_boost": env.ELEVENLABS_SIMILARITY_BOOST
    #     }
    # }
    
    # async with httpx.AsyncClient() as client:
    #     response = await client.post(url, json=data, headers=headers, timeout=3600000.0)
    #     if response.status_code != 200:
    #         raise HTTPException(status_code=response.status_code, detail="Failed to generate speech")
    #     return response.content

    tts = gTTS(text=text, lang='en')
    logger.info(colored("Write MP3 to RAM", "green", attrs=["bold"]))
    mp3_fp = BytesIO()
    tts.write_to_fp(mp3_fp)
    mp3_fp.seek(0)
    logger.info(colored("Convert MP3 in RAM to standard WAV", "green", attrs=["bold"]))
    sound = AudioSegment.from_file(mp3_fp, format="mp3")
    sound = sound.set_channels(1).set_frame_rate(16000)
    logger.info(colored(f"Export WAV to {path}", "green", attrs=["bold"]))
    sound.export(path, format="wav")

async def speech_to_text(audio_file: UploadFile) -> str:
    # """Convert speech to text using ElevenLabs API"""
    # # Save uploaded file temporarily
    # with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
    #     content = await audio_file.read()
    #     temp_file.write(content)
    #     temp_file_path = temp_file.name
    
    # try:
    #     # ElevenLabs Speech-to-Text API
    #     url = f"{ELEVENLABS_BASE_URL}/speech-to-text"
    #     headers = {
    #         "xi-api-key": ELEVENLABS_API_KEY
    #     }
        
    #     with open(temp_file_path, 'rb') as f:
    #         files = {"audio": f}
    #         data = {"model_id": "eleven_multilingual_sts_v2"}
            
    #         async with httpx.AsyncClient() as client:
    #             response = await client.post(url, files=files, data=data, headers=headers, timeout=3600000.0)
    #             if response.status_code != 200:
    #                 raise HTTPException(status_code=response.status_code, detail="Failed to convert speech to text")
                
    #             result = response.json()
    #             return result.get("text", "")
    # finally:
    #     # Clean up temporary file
    #     os.unlink(temp_file_path)

    r = sr.Recognizer()
    with sr.AudioFile(audio_file) as source:
        audio = r.record(source)

    try:
        result = r.recognize_google(audio, language="en-US")
        logger.info(colored(f"📝 Result: {result}", "green", attrs=["bold"]))
    except sr.UnknownValueError:
        logger.error(colored("❌ Cannot recognize speech.", "red", attrs=["bold"]))
    except sr.RequestError as e:
        logger.error(colored(f"⚠️ Error calling Google Speech API: {e}", "yellow", attrs=["bold"]))

AiRouter = APIRouter(
    prefix="/ai", tags=["Chat AI"]
)

Router = APIRouter()

cache = TTLCache(maxsize=500, ttl=300)


@AiRouter.post("/chat/text", response_model=ChatResponse)
async def chat_text(request: ChatRequestAPI, background_tasks: BackgroundTasks):
    """Process a text chat message and return response with audio file"""
    try:
        # Lấy prompt từ file JSON nếu có chatId
        logger.info(f'⚙️  sessionId: {request.sessionId} | message: {request.message}')
        logger.info(f'🔑 Token received: {request.token[:10] if request.token else "None"}...')
        
        agent = ManagerAgent(
            temperature=0.2,
            model=env.MODEL_NAME,
            verbose=True,
            session_id=request.sessionId,
            conversation_id=request.conversationId,
            max_iteration=env.MAX_ITERATIONS
        )

        # Check if this is a plan selection and retrieve cached plan options
        session_key = f"{request.sessionId}_{request.conversationId}"   
        cached_plans = session_cache.get(session_key)
        
        # Pass cached plans to the manager agent if available
        context = {}
        if cached_plans:
            context['cached_plan_options'] = cached_plans
        
        input_data = {
            "input": request.message,
            "token": request.token
        }
        
        logger.info(f'📤 Input data token: {input_data.get("token", "None")[:10]}...')
        
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
            # audio_filename = f"response_{request.sessionId}_{request.conversationId}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
            # temp_audio_path = f"/tmp/{audio_filename}"
            # await text_to_speech(response_text, temp_audio_path)
            # audio_content = await text_to_speech(response_text)
            
            
            # with open(temp_audio_path, 'wb') as f:
            #     f.write(audio_content)
            
            # Add audio file info to response
            response_with_audio = ChatResponse(
                sessionId=request.sessionId,
                response=response_text,
                error_status="success" if response.get('success', True) else "error",
                # audio_file_url=f"/ai/download/audio/{audio_filename}"
            )
            
            # Schedule cleanup of temporary file after some time
            # background_tasks.add_task(cleanup_temp_file, temp_audio_path, delay=3600000)  # 1 hour
            
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
        # Log to Langfuse
        try:
            span = langfuse.start_span(name="Chat Text API Error")
            span.update(
                input={
                    "sessionId": request.sessionId,
                    "conversationId": request.conversationId,
                    "message": request.message[:100] + "..." if len(request.message) > 100 else request.message,
                    "token": request.token[:10] + "..." if request.token else None
                },
                output={
                    "error": str(e),
                    "traceback": traceback.format_exc()
                },
                metadata={
                    "endpoint": "/ai/chat/text",
                    "error_type": type(e).__name__
                }
            )
            span.end()
        except Exception as trace_e:
            logger.error(f"Failed to send trace to Langfuse: {trace_e}")
        return ChatResponse(
            sessionId=request.sessionId,
            response="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại.",
            error_status="error"
        )

@AiRouter.post("/chat/audio")
async def chat_audio(
    sessionId: str,
    conversationId: str,
    token: str,
    audio_file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    """Process an audio chat message and return response with both text and audio"""
    try:
        logger.info(f'🎵 Audio chat - sessionId: {sessionId} | file: {audio_file.filename}')
        
        # Validate audio file
        if not audio_file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # Convert audio to text
        transcribed_text = await speech_to_text(audio_file)
        logger.info(f'📝 Transcribed text: {transcribed_text}')
        
        if not transcribed_text.strip():
            raise HTTPException(status_code=400, detail="Could not transcribe audio")
        
        # Process the transcribed text through the chatbot
        agent = ManagerAgent(
            temperature=0.2,
            model=env.MODEL_NAME,
            verbose=True,
            session_id=sessionId,
            conversation_id=conversationId
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
            "token": token
        }
        
        # Manager Agent handles all routing internally
        response = agent.invoke(input_data, context=context)

        # Store plan options in cache if response contains them
        if 'plan_options' in response:
            session_cache[session_key] = response['plan_options']
            logger.info(f"💾 Stored plan options for session {session_key}")

        # logger.info(f'📝 Response: {response}')
        
        response_text = response.get('output', 'Request processed successfully')
        
        # Generate audio file from response text
        audio_filename = f"response_{sessionId}_{conversationId}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        temp_audio_path = f"/tmp/{audio_filename}"
        await text_to_speech(response_text, temp_audio_path)
        # audio_content = await text_to_speech(response_text)

        # # Save audio file temporarily
        # audio_filename = f"response_{sessionId}_{conversationId}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        # temp_audio_path = f"/tmp/{audio_filename}"
        
        # with open(temp_audio_path, 'wb') as f:
        #     f.write(audio_content)
        
        # Schedule cleanup of temporary file after some time
        if background_tasks:
            background_tasks.add_task(cleanup_temp_file, temp_audio_path, delay=3600)  # 1 hour
        
        return {
            "sessionId": sessionId,
            "transcribed_text": transcribed_text,
            "response": response_text,
            "error_status": "success" if response.get('success', True) else "error",
            "audio_file_url": f"/ai/download/audio/{audio_filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing audio chat request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại."
        )

@AiRouter.get("/download/audio/{filename}")
async def download_audio(filename: str):
    """Download generated audio file"""
    file_path = f"/tmp/{filename}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="audio/wav"
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
    Retrieve the MCP server token from environment variables
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