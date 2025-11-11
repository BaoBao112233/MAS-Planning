

speech_file_path = "test_folders/output.wav" 
model = "playai-tts" # "playai-tts-arabic"
voice = "Fritz-PlayAI"
# Arista-PlayAI, Atlas-PlayAI, Basil-PlayAI, Briggs-PlayAI, Calum-PlayAI, Celeste-PlayAI, Cheyenne-PlayAI, Chip-PlayAI, 
# Cillian-PlayAI, Deedee-PlayAI, Fritz-PlayAI, Gail-PlayAI, Indigo-PlayAI, Mamaw-PlayAI, Mason-PlayAI, Mikail-PlayAI, 
# Mitch-PlayAI, Quinn-PlayAI, Thunder-PlayAI

import os
import tempfile
from groq import Groq
from fastapi import UploadFile, HTTPException
from termcolor import colored
import logging
from template.configs.environments import env

logger = logging.getLogger(__name__)

# Khởi tạo Groq client
CLIENT = Groq(api_key=env.GROQ_API_KEY)

async def speech_to_text(client: Groq, audio_file: UploadFile) -> str:
    """Convert speech to text using Groq Whisper API"""
    temp_file_path = None
    
    try:
        logger.info(colored("🎧 Converting speech to text with Groq Whisper...", "green", attrs=["bold"]))
        
        # Lưu file tạm thời
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            content = await audio_file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        # Đọc file và gọi Groq Whisper API
        with open(temp_file_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(temp_file_path, file.read()),
                model=env.GROQ_MODEL_STT,
                temperature=0,
                response_format="verbose_json",
            )
            
            result = transcription.text
            logger.info(colored(f"📝 Transcription result: {result}", "green", attrs=["bold"]))
            return result
            
    except Exception as e:
        logger.error(colored(f"❌ Error transcribing audio: {e}", "red", attrs=["bold"]))
        raise HTTPException(status_code=500, detail=f"Failed to convert speech to text: {str(e)}")
        
    finally:
        # Xóa file tạm
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.info(colored("🗑️ Temporary file cleaned up", "yellow"))
            except Exception as e:
                logger.warning(colored(f"⚠️ Failed to delete temporary file: {e}", "yellow"))


# Danh sách voices có sẵn từ Groq PlayAI
AVAILABLE_VOICES = [
    "Arista-PlayAI", "Atlas-PlayAI", "Basil-PlayAI", "Briggs-PlayAI", 
    "Calum-PlayAI", "Celeste-PlayAI", "Cheyenne-PlayAI", "Chip-PlayAI",
    "Cillian-PlayAI", "Deedee-PlayAI", "Fritz-PlayAI", "Gail-PlayAI",
    "Indigo-PlayAI", "Mamaw-PlayAI", "Mason-PlayAI", "Mikail-PlayAI",
    "Mitch-PlayAI", "Quinn-PlayAI", "Thunder-PlayAI"
]


async def text_to_speech_with_voice(client: Groq, text: str, path: str, voice: str = "Fritz-PlayAI"):
    """Convert text to speech using Groq API with custom voice selection"""
    if voice not in AVAILABLE_VOICES:
        logger.warning(colored(f"⚠️ Voice '{voice}' not available. Using default 'Fritz-PlayAI'", "yellow"))
        voice = "Fritz-PlayAI"
    
    try:
        logger.info(colored(f"🎤 Generating speech with voice: {voice}", "green", attrs=["bold"]))
        
        response = client.audio.speech.create(
            model=env.GROQ_MODEL_VOICE_1,
            voice=voice,
            input=text,
            response_format="wav"
        )
        
        logger.info(colored(f"💾 Export WAV to {path}", "green", attrs=["bold"]))
        response.write_to_file(path)
        
        logger.info(colored("✅ Speech generation completed", "green", attrs=["bold"]))
        
    except Exception as e:
        logger.error(colored(f"❌ Error generating speech: {e}", "red", attrs=["bold"]))
        raise HTTPException(status_code=500, detail=f"Failed to generate speech: {str(e)}")