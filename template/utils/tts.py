import os
import tempfile
import logging
import wave
from typing import Dict, List, Optional
from fastapi import UploadFile, HTTPException
from termcolor import colored
from google.cloud import texttospeech, speech
from template.configs.environments import env

logger = logging.getLogger(__name__)

CLIENT_CONFIG = {"api_key": env.GOOGLE_API_KEY}

# Cache for available voices
_VOICES_CACHE: Optional[Dict] = None

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
    """Convert speech to text using Google Cloud Speech-to-Text"""
    temp_file_path = None
    logger.info(colored("🎧 Converting speech to text with Google Speech-to-Text...", "green", attrs=["bold"]))
    logger.info(colored(f"Client config: {CLIENT_CONFIG}", "green", attrs=["bold"]))
    try:
        # Lưu file tạm thời
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            content = await audio_file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        # Detect sample rate từ WAV file
        sample_rate = get_wav_sample_rate(temp_file_path) if temp_file_path.endswith(".wav") else 16000
        
        # Đọc file
        with open(temp_file_path, "rb") as f:
            content = f.read()

        client = speech.SpeechClient(client_options=CLIENT_CONFIG)
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16
            if temp_file_path.endswith(".wav")
            else speech.RecognitionConfig.AudioEncoding.MP3,
            sample_rate_hertz=sample_rate,  # Sử dụng sample rate đã detect
            language_code="vi-VN",
            enable_automatic_punctuation=True,
        )

        response = client.recognize(config=config, audio=audio)
        result = " ".join([r.alternatives[0].transcript for r in response.results])

        logger.info(colored(f"📝 Transcription result: {result}", "green", attrs=["bold"]))
        return result

    except Exception as e:
        logger.error(colored(f"❌ Error transcribing audio: {e}", "red", attrs=["bold"]))
        raise HTTPException(status_code=500, detail=f"Failed to convert speech to text: {str(e)}")

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.info(colored("🗑️ Temporary file cleaned up", "yellow"))
            except Exception as e:
                logger.warning(colored(f"⚠️ Failed to delete temporary file: {e}", "yellow"))


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
        client = texttospeech.TextToSpeechClient(client_options=CLIENT_CONFIG)
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
    Convert text to speech using Google Cloud TTS with hierarchical voice selection.
    
    Args:
        text: Text to convert to speech
        path: Output file path for the audio
        voice_name: Full voice name (e.g., "vi-VN-Neural2-A")
        language_code: Language code (e.g., "vi-VN")
    """
    logger.info(colored(f"Client config: {CLIENT_CONFIG}", "green", attrs=["bold"]))
    
    try:            
        logger.info(colored(
            f"🎤 Generating speech with Google TTS\n"
            f"   Language: {language_code}\n"
            f"   Voice: {voice_name}\n"
            f"   Text: {text[:50]}...",
            "green", attrs=["bold"]
        ))
        
        client = texttospeech.TextToSpeechClient(client_options=CLIENT_CONFIG)
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16
        )

        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config
        )

        # Lưu file WAV
        with open(path, "wb") as out:
            out.write(response.audio_content)

        logger.info(colored(f"💾 Export WAV to {path}", "green", attrs=["bold"]))
        logger.info(colored("✅ Speech generation completed", "green", attrs=["bold"]))

    except Exception as e:
        error_message = str(e).lower()
        logger.error(colored(f"❌ Error generating speech: {e}", "red", attrs=["bold"]))
        
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
