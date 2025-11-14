import os
import tempfile
import logging
import wave
import re
from typing import Dict, List, Optional
from fastapi import UploadFile, HTTPException
from termcolor import colored
from google.cloud import texttospeech, speech
from template.configs.environments import env

logger = logging.getLogger(__name__)

CLIENT_CONFIG = {"api_key": env.GOOGLE_API_KEY}

# Cache for available voices
_VOICES_CACHE: Optional[Dict] = None

# Reusable clients for better performance
_TTS_CLIENT: Optional[texttospeech.TextToSpeechClient] = None
_STT_CLIENT: Optional[speech.SpeechClient] = None


def get_tts_client() -> texttospeech.TextToSpeechClient:
    """Get or create reusable TTS client"""
    global _TTS_CLIENT
    if _TTS_CLIENT is None:
        _TTS_CLIENT = texttospeech.TextToSpeechClient(client_options=CLIENT_CONFIG)
    return _TTS_CLIENT


def get_stt_client() -> speech.SpeechClient:
    """Get or create reusable STT client"""
    global _STT_CLIENT
    if _STT_CLIENT is None:
        _STT_CLIENT = speech.SpeechClient(client_options=CLIENT_CONFIG)
    return _STT_CLIENT


def clean_text_for_tts(text: str) -> str:
    """
    Clean text before sending to TTS by removing unnecessary characters.
    
    Removes:
    - Markdown formatting (**, __, *, _, [], (), etc.)
    - Emoji and special symbols
    - Multiple spaces
    - HTML tags
    - Special punctuation that TTS doesn't handle well
    
    Args:
        text: Raw text with markdown/emoji/symbols
        
    Returns:
        Cleaned text suitable for TTS
    """
    if not text:
        return text
    
    # Remove markdown bold/italic (**text**, __text__, *text*, _text_)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'__(.+?)__', r'\1', text)      # __bold__
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # *italic*
    text = re.sub(r'_(.+?)_', r'\1', text)        # _italic_
    
    # Remove markdown headers (##, ###, etc.)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # Remove markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove markdown code blocks ```code``` -> code
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove bullet points and list markers
    text = re.sub(r'^[\s]*[•\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)
    
    # Remove emoji (Unicode ranges for emoji)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"
        "]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)
    
    # Remove special symbols and icons (🏠, 🤖, ✅, ❌, etc.)
    text = re.sub(r'[🏠🤖🔧🧠📋⚙️🔑🎤🌍🎙️✅❌⚠️🔴🟡📅⏰💡🔥🎯]', '', text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove XML tags (like <reasoning>, <agent_type>, etc.)
    text = re.sub(r'</?[a-zA-Z_]+>', '', text)
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)  # Multiple spaces -> single space
    text = re.sub(r'\n\s*\n', '\n', text)  # Multiple newlines -> single newline
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    return text

def get_wav_sample_rate(file_path: str) -> int:
    """Detect sample rate from WAV file"""
    try:
        with wave.open(file_path, 'rb') as wav_file:
            sample_rate = wav_file.getframerate()
            logger.info(colored(f"🎵 Detected sample rate: {sample_rate}Hz", "cyan", attrs=["bold"]))
            return sample_rate
    except Exception as e:
        logger.warning(colored(f"⚠️ Could not detect sample rate: {e}, using default 16000Hz", "yellow"))
        return 16000

async def speech_to_text(audio_file: UploadFile) -> str:
    """Convert speech to text using Google Cloud Speech-to-Text (optimized)"""
    temp_file_path = None
    try:
        # Determine file extension from content type or filename
        content_type = audio_file.content_type or ""
        filename = audio_file.filename or ""
        
        # Determine appropriate file extension
        if "webm" in content_type or filename.endswith(".webm"):
            suffix = ".webm"
        elif "mp3" in content_type or filename.endswith(".mp3"):
            suffix = ".mp3"
        elif "wav" in content_type or filename.endswith(".wav"):
            suffix = ".wav"
        elif "ogg" in content_type or filename.endswith(".ogg"):
            suffix = ".ogg"
        else:
            # Default to webm as it's common for browser recordings
            suffix = ".webm"
            logger.warning(f"⚠️ Unknown audio format: {content_type} / {filename}, defaulting to .webm")
        
        # Save temporary file with correct extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            content = await audio_file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        logger.info(f"🎵 Processing audio file: {temp_file_path} (original: {filename})")

        # Detect sample rate and encoding based on file type
        if suffix == ".wav":
            sample_rate = get_wav_sample_rate(temp_file_path)
            encoding = speech.RecognitionConfig.AudioEncoding.LINEAR16
        elif suffix == ".mp3":
            sample_rate = 48000  # Common for MP3
            encoding = speech.RecognitionConfig.AudioEncoding.MP3
        elif suffix == ".webm" or suffix == ".ogg":
            sample_rate = 48000  # Common for WebM/Ogg
            encoding = speech.RecognitionConfig.AudioEncoding.OGG_OPUS
        else:
            sample_rate = 16000
            encoding = speech.RecognitionConfig.AudioEncoding.LINEAR16
        
        # Read file content
        with open(temp_file_path, "rb") as f:
            content = f.read()

        # Check if content is not empty
        if len(content) == 0:
            logger.error("❌ Audio file is empty (0 bytes)")
            return ""

        logger.info(f"📊 Audio size: {len(content)} bytes, sample_rate: {sample_rate}, encoding: {encoding}")

        # Use reusable client
        client = get_stt_client()
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=encoding,
            sample_rate_hertz=sample_rate,
            language_code="vi-VN",
            enable_automatic_punctuation=True,
            use_enhanced=True,  # Use better model
            model="latest_short",  # Optimized for short audio
        )

        response = client.recognize(config=config, audio=audio)
        
        # Check if we got any results
        if not response.results:
            logger.warning(colored("⚠️ STT returned no results - audio may be silent or unrecognizable", "yellow"))
            return ""
        
        result = " ".join([r.alternatives[0].transcript for r in response.results])

        if result.strip():
            logger.info(colored(f"📝 STT result: {result[:100]}...", "green"))
        else:
            logger.warning(colored("⚠️ STT result is empty after transcription", "yellow"))
        
        return result

    except Exception as e:
        logger.error(colored(f"❌ STT error: {e}", "red"))
        raise HTTPException(status_code=500, detail=f"Failed to convert speech to text: {str(e)}")

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(colored(f"⚠️ Failed to delete temp file: {e}", "yellow"))


def get_available_voices() -> Dict[str, Dict[str, List[Dict]]]:
    """
    Fetch all available voices from Google Cloud TTS API and structure them hierarchically.
    
    Returns:
        Dict structure: {
            "language_code": {
                "model_type": [
                    {
                        "name": "voice-name",
                        "gender": "MALE/FEMALE/NEUTRAL",
                        "natural_sample_rate_hertz": 24000
                    }
                ]
            }
        }
    """
    global _VOICES_CACHE
    
    # Return cached voices if available
    if _VOICES_CACHE is not None:
        logger.info(colored("📦 Returning cached voice list", "cyan", attrs=["bold"]))
        return _VOICES_CACHE
    
    try:
        logger.info(colored("🔍 Fetching available voices from Google Cloud TTS...", "cyan", attrs=["bold"]))
        client = get_tts_client()  # Sử dụng reusable client
        response = client.list_voices()
        
        # Structure: {language_code: {model_type: [voices]}}
        structured_voices: Dict[str, Dict[str, List[Dict]]] = {}
        
        for voice in response.voices:
            for language_code in voice.language_codes:
                # Initialize language if not exists
                if language_code not in structured_voices:
                    structured_voices[language_code] = {}
                
                # Determine model type from voice name
                voice_name = voice.name
                if "Chirp3-HD" in voice_name:
                    model_type = "Chirp3-HD"
                elif "Chirp-HD" in voice_name:
                    model_type = "Chirp-HD"
                elif "Neural2" in voice_name:
                    model_type = "Neural2"
                elif "Wavenet" in voice_name or "WaveNet" in voice_name:
                    model_type = "WaveNet"
                elif "Studio" in voice_name:
                    model_type = "Studio"
                elif "Standard" in voice_name:
                    model_type = "Standard"
                elif "News" in voice_name:
                    model_type = "News"
                elif "Polyglot" in voice_name:
                    model_type = "Polyglot"
                elif "Casual" in voice_name:
                    model_type = "Casual"
                else:
                    model_type = "Other"
                
                # Initialize model type if not exists
                if model_type not in structured_voices[language_code]:
                    structured_voices[language_code][model_type] = []
                
                # Extract voice name (last part after model type)
                # Example: "en-US-Chirp3-HD-Despina" -> "Despina"
                voice_parts = voice_name.split('-')
                short_name = voice_parts[-1] if len(voice_parts) > 0 else voice_name
                
                # Add voice info with enhanced structure
                voice_info = {
                    "lang_code": language_code,
                    "model": model_type,
                    "name": short_name,
                    "voice_name": voice_name,
                    "gender": voice.ssml_gender.name if voice.ssml_gender else "NEUTRAL",
                    "natural_sample_rate_hertz": voice.natural_sample_rate_hertz if voice.natural_sample_rate_hertz else 24000
                }
                
                structured_voices[language_code][model_type].append(voice_info)
        
        # Cache the result
        _VOICES_CACHE = structured_voices
        
        # Log summary
        total_voices = sum(len(voices) for lang in structured_voices.values() for voices in lang.values())
        logger.info(colored(
            f"✅ Fetched {total_voices} voices across {len(structured_voices)} languages",
            "green", attrs=["bold"]
        ))
        
        return structured_voices
        
    except Exception as e:
        logger.error(colored(f"❌ Error fetching voices: {e}", "red", attrs=["bold"]))
        raise HTTPException(status_code=500, detail=f"Failed to fetch available voices: {str(e)}")


async def text_to_speech_with_voice(
    text: str, 
    path: str, 
    voice_name: str = "vi-VN-Neural2-A",
    language_code: str = "vi-VN"
):
    """
    Convert text to speech using Google Cloud TTS (optimized for speed).
    
    Args:
        text: Text to convert to speech (will be cleaned automatically)
        path: Output file path for the audio
        voice_name: Full voice name (e.g., "vi-VN-Neural2-A")
        language_code: Language code (e.g., "vi-VN")
    """
    try:
        # Clean text before TTS
        cleaned_text = clean_text_for_tts(text)
        
        # Minimal logging
        if len(text) != len(cleaned_text):
            logger.info(colored(
                f"🧹 Text cleaned: {len(text)} → {len(cleaned_text)} chars",
                "yellow"
            ))
        
        # Sử dụng reusable client
        client = get_tts_client()
        synthesis_input = texttospeech.SynthesisInput(text=cleaned_text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        )
        
        # Sử dụng MP3 (nhẹ hơn LINEAR16) và tăng tốc độ đọc
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.15,  # Đọc nhanh hơn 15%
            pitch=0.0,
        )

        # Gọi API
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config
        )

        # Lưu file MP3
        with open(path, "wb") as out:
            out.write(response.audio_content)

        logger.info(colored(f"✅ TTS completed: {path}", "green"))

    except Exception as e:
        error_message = str(e).lower()
        logger.error(colored(f"❌ TTS error: {e}", "red"))
        
        if any(keyword in error_message for keyword in ["rate", "quota", "limit", "429"]):
            raise HTTPException(
                status_code=429,
                detail="TTS service rate limit exceeded. Please try again later."
            )
        elif "invalid" in error_message or "not found" in error_message:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid voice configuration: {voice_name} for language {language_code}"
            )
        else:
            raise HTTPException(status_code=500, detail=f"Failed to generate speech: {str(e)}")
