import time
from datetime import datetime
from pydantic import BaseModel
from template.configs.environments import env
import requests

# Schema for get_weather tool
class GetWeatherInput(BaseModel):
    """Input schema for get_weather tool"""
    city: str = "Hanoi"

# Schema for get_current_time tool (no input required)
class GetCurrentTimeInput(BaseModel):
    """Input schema for get_current_time tool - no parameters needed"""
    pass


def get_current_time():
    """Get the current time"""
    now = datetime.now()
    return now.strftime("%d/%m/%Y %H:%M:%S")

def get_weather(city: str, language_code: str = "vi-VN"):
    """Get current weather for a given city using OpenWeatherMap API with language support."""
    OPEN_WEATHER_API_KEY = env.OPEN_WEATHER_API_KEY
    if not OPEN_WEATHER_API_KEY:
        if language_code.startswith('vi'):
            return "Khóa API OpenWeatherMap chưa được cấu hình."
        return "OpenWeatherMap API key is not configured."

    # Map language codes to OpenWeatherMap API language codes
    lang_map = {
        'vi': 'vi', 'en': 'en', 'zh': 'zh_cn', 'ja': 'ja', 'ko': 'kr',
        'fr': 'fr', 'de': 'de', 'es': 'es', 'it': 'it', 'pt': 'pt_br',
        'ru': 'ru', 'ar': 'ar', 'hi': 'hi', 'th': 'th'
    }
    
    # Extract language prefix from language_code (e.g., 'vi-VN' -> 'vi')
    lang_prefix = language_code.split('-')[0].lower()
    api_lang = lang_map.get(lang_prefix, 'vi')  # Default to Vietnamese

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPEN_WEATHER_API_KEY}&units=metric&lang={api_lang}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if data.get("cod") != 200:
            if language_code.startswith('vi'):
                return f"Lỗi khi lấy dữ liệu thời tiết: {data.get('message', 'Lỗi không xác định')}"
            return f"Error fetching weather data: {data.get('message', 'Unknown error')}"

        weather_description = data["weather"][0]["description"]
        temperature = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"]

        # Format response based on language
        if language_code.startswith('vi'):
            weather_info = (
                f"Thời tiết tại {city}:\n"
                f"- Mô tả: {weather_description}\n"
                f"- Nhiệt độ: {temperature}°C\n"
                f"- Độ ẩm: {humidity}%\n"
                f"- Tốc độ gió: {wind_speed} m/s"
            )
        else:
            weather_info = (
                f"Weather in {city}:\n"
                f"- Description: {weather_description}\n"
                f"- Temperature: {temperature}°C\n"
                f"- Humidity: {humidity}%\n"
                f"- Wind Speed: {wind_speed} m/s"
            )
        return weather_info

    except requests.RequestException as e:
        if language_code.startswith('vi'):
            return f"Lỗi khi kết nối đến dịch vụ thời tiết: {str(e)}"
        return f"Error connecting to weather service: {str(e)}"