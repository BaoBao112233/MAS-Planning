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

async def ac_controls_mesh(serial_numbers: List[str], net_index: int, app_index: int, vendor: str, power: str, mode: str, temp: str, fan_speed: str, swing_h: str, swing_v: str, quiet: str = None, turbo: str = None, econo: str = None, light: str = None, filter: str = None, clean: str = None, beep: str = None, sleep: int = None, model: int = None, celsius: str = "on"):
    """Send AC IR control commands via BLE Mesh network for CONDITIONER devices
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        serial_numbers (List[str]): Array of device serial numbers to send the command (remoteButton.device.seriNumber Eg: 'MCTRYZCGX').
        net_index (int): Network key index for the mesh network (house_id).
        app_index (int): Application key index for the mesh network (thường là 0).
        vendor (str): AC button modelName identifier (e.g., 'PANASONIC_AC', 'PANASONIC_AC32', 'SAMSUNG_AC', 'ELECTRA_AC').
        power (str): Power state: '1'/'on' for ON, '0'/'off' for OFF.
        mode (str): AC operating mode ('1'/'auto', '2'/'heat', '3'/'cool', '4'/'dry', '5'/'fan').
        temp (str): Target temperature value ("16" to "32").
        fan_speed (str): Fan speed ('0'/'auto', '1'/'low', '2'/'medium', '3'/'high', '4'/'turbo').
        swing_h (str): Horizontal swing: '1'/'on' for ON, '0'/'off' for OFF.
        swing_v (str): Vertical swing: '1'/'on' for ON, '0'/'off' for OFF.
        quiet (str, optional): Quiet mode: 'on' or 'off'.
        turbo (str, optional): Turbo mode: 'on' or 'off'.
        econo (str, optional): Economy mode: 'on' or 'off'.
        light (str, optional): Display light: 'on' or 'off'.
        filter (str, optional): Filter indicator: 'on' or 'off'.
        clean (str, optional): Clean mode: 'on' or 'off'.
        beep (str, optional): Beep sound: 'on' or 'off'.
        sleep (int, optional): Sleep timer value (-1 for off).
        model (int, optional): Model number.
        celsius (str, optional): Temperature unit: 'on' for Celsius. Default is 'on'.
    """

    logger.info(f"AC controls mesh: {serial_numbers}, {vendor}, {power}, {mode}, {temp}, {fan_speed}")
    try:
        # Chuẩn bị dữ liệu cho AC control
        data = {
            "Vendor": vendor,
            "Power": power,
            "Mode": mode,
            "Temp": temp,
            "FanSpeed": fan_speed,
            "SwingH": swing_h,
            "SwingV": swing_v
        }
        
        # Thêm các tham số tùy chọn nếu được cung cấp
        if quiet is not None:
            data["Quiet"] = quiet
        if turbo is not None:
            data["Turbo"] = turbo
        if econo is not None:
            data["Econo"] = econo
        if light is not None:
            data["Light"] = light
        if filter is not None:
            data["Filter"] = filter
        if clean is not None:
            data["Clean"] = clean
        if beep is not None:
            data["Beep"] = beep
        if sleep is not None:
            data["Sleep"] = sleep
        if model is not None:
            data["Model"] = model
        if celsius is not None:
            data["Celsius"] = celsius

        # Chuẩn bị payload cho API
        payload = {
            "serial_number": serial_numbers,
            "meshIndex": {
                "net_Index": net_index,
                "app_Index": app_index
            },
            "command_type": 216,  # Command type cố định cho AC control
            "data": data
        }
        
        # Gọi API để điều khiển điều hòa
        url = env.OXII_ROOT_API_URL + "/api/app/device/switch/ac-controls-mesh"
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            'X-Origin': 'smarthiz'
        }

        logger.info(f"AC controls mesh payload: {payload}")
        response = await http_client.put(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"AC controls mesh response: {response.json()}")
        logger.info("-------------------------------------")
        
        return "Đã gửi lệnh điều khiển điều hòa thành công"
    except Exception as e:
        logger.error(f"Lỗi khi gửi lệnh điều khiển điều hòa: {str(e)}")
        raise

async def ac_controls_mesh_v2(buttonId: int, power: str, mode: str='1', temp: str='24', fan_speed: str='0', swing_h: str='0', swing_v: str='0'):
    """Send AC IR control commands via BLE Mesh network for CONDITIONER devices
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        buttonId (int): ID of the remote button.
        power (str): Power state: '1'/'on' for ON, '0'/'off' for OFF.
        mode (str): AC operating mode ('1'/'auto', '2'/'heat', '3'/'cool', '4'/'dry', '5'/'fan'). Default is '1'.
        temp (str): Target temperature value ("16" to "32"). Default is '25'.
        fan_speed (str): Fan speed ('0'/'auto', '1'/'low', '2'/'medium', '3'/'high', '4'/'turbo'). Default is '1'.
        swing_h (str): Horizontal swing: '1'/'on' for ON, '0'/'off' for OFF. Default is '0'.
        swing_v (str): Vertical swing: '1'/'on' for ON, '0'/'off' for OFF. Default is '0'.
    """

    room_info = await get_device_list(env.OXII_API_KEY)
    room_info = json.loads(room_info)

    button_info = None
    for room in room_info:
        for button in room['buttons']:
            if button['buttonId'] == buttonId:
                button_info = button
                break

    if button_info is None:
        raise ValueError(f"Không tìm thấy thông tin của nút bấm với buttonId: {buttonId}")

    vendor = button_info['modelName']
    serial_numbers = [button_info['seriNumber']]
    net_index = button_info['net_Index']
    app_index = button_info['app_Index']
    
    logger.info(f"AC controls mesh: {buttonId}, {serial_numbers}, {vendor}, {power}, {mode}, {temp}, {fan_speed}")
    try:
        # Chuẩn bị dữ liệu cho AC control
        data = {
            "Vendor": vendor,
            "Power": power,
            "Mode": mode,
            "Temp": temp,
            "FanSpeed": fan_speed,
            "SwingH": swing_h,
            "SwingV": swing_v
        }

        # Chuẩn bị payload cho API
        payload = {
            "serial_number": serial_numbers,
            "meshIndex": {
                "net_Index": net_index,
                "app_Index": app_index
            },
            "command_type": 216,  # Command type cố định cho AC control
            "data": data
        }
        
        # Gọi API để điều khiển điều hòa
        url = env.OXII_ROOT_API_URL + "/api/app/device/switch/ac-controls-mesh"
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            'X-Origin': 'smarthiz'
        }

        logger.info(f"AC controls mesh payload: {payload}")
        response = await http_client.put(url, headers=headers, json=payload)
        response.raise_for_status()
        logger.info(f"AC controls mesh response: {response.json()}")
        logger.info("-------------------------------------")
        
        return "Đã gửi lệnh điều khiển điều hòa thành công"
    except Exception as e:
        logger.error(f"Lỗi khi gửi lệnh điều khiển điều hòa: {str(e)}")
        raise

