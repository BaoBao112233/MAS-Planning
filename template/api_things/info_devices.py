import requests
import json
from typing import List
import time
import os
import logging
import threading

from template.api_things.common import cron_to_custom_format
from template.configs.environments import env

try:
    from toon_format import encode
    TOON_AVAILABLE = True
except ImportError:
    TOON_AVAILABLE = False
    logging.warning("toon-format not installed. TOON format will not be available.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

# Biến lưu trữ cronjob tạm thời để xử lý các tác vụ đồng thời
temp_cronjob_cache = {}

# Khóa để đảm bảo chỉ một tác vụ truy cập vào cache tại một thời điểm
cache_lock = threading.Lock()

TIME_RETRY = 30

def get_device_list(is_format_toon: bool = True):
    """
    Get status of devices in the house from Oxii API.
    
    Args:
        is_format_toon (bool): If True, convert to TOON format (default True). 
                               If False, return as JSON string.

    Returns:
        str: List of devices in the house (TOON format if is_format_toon=True, JSON otherwise).
    """
    
    logger.info(f"Get device list with env.OXII_API_KEY: {env.OXII_API_KEY[:10]}... (TOON format: {is_format_toon})")

    try:
        api_url = env.OXII_ROOT_API_URL + "/api/app/oxii/home"
        headers = {
            "Content-Type": "application/json",
            'X-Origin': 'smarthiz',
            'Authorization': f"Bearer {env.OXII_API_KEY}"
        }
        payload = {"query":" ","variables":{}}
        # logger.info(f"Headers: {headers}")
        response = requests.get(api_url, headers=headers, params=payload, timeout=60.0)
        response.raise_for_status()
        
        formatted_devices = []
        data = response.json()['data']
        homes = data.get('data', [])
        home = homes[0] if homes else None
        if not home:
            logger.error("Không tìm thấy thông tin nhà")
            return "Không tìm thấy thông tin nhà"

        # logger.info(f"House info: {home}")
        
        for room in home.get('rooms', []):
            room_info = {
                'house_id': home['id'],
                'room_id': room['id'],
                'room_name': room['name'],
                'devices': [],
                'buttons': []
            }

            # logger.info(f"Room info: {room}")

            for device in room.get('devices', []):
                device_info = {
                    'name': device['models']['displayName'],
                    'seriNumber': device['seriNumber'],
                    'device_status': 'Không thể kết nối' if device['status'] == 2 and device['joinMesh'] == 0 else "Đang kết nối"
                }
                room_info['devices'].append(device_info)
            
            # logger.info(f"Devices info: {room_info['devices']}")
            
            for button in room.get('remoteButtons', []):
                button_info = {
                    'buttonId': button['id'],
                    'name': button['name'],
                    'button_code': button['code'],
                    'button_type': button['type'],
                    'label': button['label'],
                    'modelName': button['modelName'],
                    'remoteIRId': button['remoteIRId'],
                    'brandId': button['brandId'],
                    'status': "bật" if button['status'] == '1' else "tắt",
                    'deviceId': button['device']['id'],
                    'seriNumber': button['device']['seriNumber'],
                    'joinMesh': button['joinMesh'],
                    'net_Index': button['device']['meshControl']['net_Index'] if button['device']['meshControl'] and 'net_Index' in button['device']['meshControl'] else None,
                    'app_Index': button['device']['meshControl']['app_Index'] if button['device']['meshControl'] and 'app_Index' in button['device']['meshControl'] else None
                }
                room_info['buttons'].append(button_info)
            
            formatted_devices.append(room_info)
            # logger.info(f"Room info: {room_info}")
            # logger.info("-------------------------------------")
        
        # Format output based on is_format_toon parameter
        if is_format_toon and TOON_AVAILABLE:
            try:
                # Convert to TOON format for compact representation
                toon_output = encode(formatted_devices)
                logger.info(f"Converted device list to TOON format ({len(toon_output)} chars)")
                return toon_output
            except Exception as e:
                logger.warning(f"Failed to convert to TOON format: {e}. Falling back to JSON.")
                return json.dumps(formatted_devices, indent=4, ensure_ascii=False)
        else:
            # Return as JSON string
            if is_format_toon and not TOON_AVAILABLE:
                logger.warning("TOON format requested but toon-format package not installed. Returning JSON.")
            return json.dumps(formatted_devices, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thiết bị: {str(e)} với env.OXII_API_KEY: {env.OXII_API_KEY}")
        raise

def get_device_info(deviceId: int):
    url = env.OXII_ROOT_API_URL + f"/api/app/oxii/device/{str(deviceId)}/properties"
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        "Authorization": f"Bearer {env.OXII_API_KEY}",
        'X-Origin': 'smarthiz'
    }
    
    response = requests.get(url, headers=headers, timeout=60.0)
    response.raise_for_status()

    return response.json()["data"]