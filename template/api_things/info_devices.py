import requests
import httpx
import json
from typing import List
import asyncio
import time
import os
import logging

from template.api_things.common import cron_to_custom_format
from template.configs.environments import env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

# Tạo một client HTTP để tái sử dụng
http_client = httpx.AsyncClient(timeout=60.0)

# Biến lưu trữ cronjob tạm thời để xử lý các tác vụ đồng thời
temp_cronjob_cache = {}

# Khóa để đảm bảo chỉ một tác vụ truy cập vào cache tại một thời điểm
cache_lock = asyncio.Lock()

TIME_RETRY = 30

async def get_device_list():
    """
    Get status of devices in the house from Oxii API.
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.

    Returns:
        str: List of devices in the house.
    """
    
    logger.info(f"Get device list with env.OXII_API_KEY: {env.OXII_API_KEY}")

    try:
        api_url = env.OXII_ROOT_API_URL + "/api/app/oxii/home"
        headers = {
            "Content-Type": "application/json",
            'X-Origin': 'smarthiz',
            'Authorization': f"Bearer {env.OXII_API_KEY}"
        }
        payload = {"query":" ","variables":{}}
        logger.info(f"Headers: {headers}")
        response = await http_client.get(api_url, headers=headers, params=payload)
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
            logger.info(f"Room info: {room_info}")
            logger.info("-------------------------------------")
        return json.dumps(formatted_devices, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thiết bị: {str(e)} với env.OXII_API_KEY: {env.OXII_API_KEY}")
        raise

async def get_device_info(deviceId: int):
    url = env.OXII_ROOT_API_URL + f"/api/app/oxii/device/{str(deviceId)}/properties"
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        "Authorization": f"Bearer {env.OXII_API_KEY}",
        'X-Origin': 'smarthiz'
    }
    
    response = await http_client.get(url, headers=headers)
    response.raise_for_status()

    return response