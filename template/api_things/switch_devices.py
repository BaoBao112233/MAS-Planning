import requests
import json
from typing import List
import time
import os
import logging
import threading

from template.api_things.common import cron_to_custom_format
from template.configs.environments import env
from template.api_things.info_devices import get_device_info, get_device_list

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

def switch_on_off_all_device(command: str):
    """Turn on off all devices in a house using one-touch control
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        command (str): Command to send (on, off).
    """
    logger.info(f"Switch on all device with env.OXII_API_KEY: {env.OXII_API_KEY}")
    try:
        room_info = get_device_list()
        room_info = json.loads(room_info)

        # Lấy thông tin về house_id
        house_id = room_info[0]['house_id']

        headers = {
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            "Content-Type": "application/json",
            'X-Origin': 'smarthiz'
        }
        
        # Gọi API one-touch để bật tất cả thiết bị
        if command.upper() == 'OFF':
            one_touch_url = env.OXII_ROOT_API_URL + f"/api/app/house/{house_id}/one-touch/TURN_OFF_ALL_DEVICES/execute"
            text_command = "tắt"
        else:
            one_touch_url = env.OXII_ROOT_API_URL + f"/api/app/house/{house_id}/one-touch/TURN_ON_ALL_DEVICES/execute"
            text_command = "bật"
        
        one_touch_response = requests.post(one_touch_url, headers=headers, timeout=60.0)
        one_touch_response.raise_for_status()
        
        result = one_touch_response.json()
        logger.info(f"Switch all device response: {result}")
        
        # Kiểm tra kết quả
        start_time = time.time()
        success = False
        latest_status = None
        
        while time.time() - start_time < TIME_RETRY:
            try:
                current_status = get_device_list()
                current_status = json.loads(current_status)
                latest_status = current_status
                logger.info(f"Current status: {current_status} after {time.time() - start_time} seconds")
                
                # Check if devices are in desired state
                all_devices_on = True
                for room in current_status:
                    for button in room['buttons']:
                        if button['status'] != text_command and button['remoteIRId'] is None:
                            all_devices_on = False
                            break
                    if not all_devices_on:
                        break
                
                if all_devices_on:
                    success = True
                    logger.info(f"Tất cả thiết bị đã được {text_command} thành công")
                    return f"Tất cả thiết bị đã được {text_command} thành công"
                
                # Wait 1 second before next check
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Lỗi khi kiểm tra trạng thái thiết bị: {str(e)}")
                time.sleep(1)
                continue
        
        if not success:
            logger.error(f"Chưa thể bật tất cả thiết bị. Trạng thái các thiết bị hiện tai: {latest_status}")
            return f"Chưa thể bật tất cả thiết bị. Trạng thái các thiết bị hiện tai: {latest_status}"
    
    except Exception as e:
        logger.error(f"Lỗi khi bật tất cả thiết bị: {str(e)}")
        return f"Lỗi khi bật tất cả thiết bị: {str(e)}"

def switch_device_by_type(device_type: str, action: str):
    """Turn on/off devices by type using one-touch control
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        device_type (str): Type of device (LIGHT, TV, CONDITIONER, FAN, HOT_COLD_SHOWER, SOCKET).
        action (str): Action to perform (ON, OFF).
    """
    logger.info(f"Switch {device_type} {action} with env.OXII_API_KEY: {env.OXII_API_KEY}")
    try:
        # Kiểm tra tham số đầu vào
        device_type = device_type.upper()
        action = action.upper()
        
        # Kiểm tra loại thiết bị hợp lệ
        valid_device_types = ["LIGHT", "TV", "CONDITIONER", "FAN", "HOT_COLD_SHOWER", "SOCKET"]
        if device_type not in valid_device_types:
            logger.error(f"Loại thiết bị không hợp lệ: {device_type}")
            return f"Loại thiết bị không hợp lệ. Các loại hợp lệ: {', '.join(valid_device_types)}"
        
        # Kiểm tra hành động hợp lệ
        if action not in ["ON", "OFF"]:
            logger.error(f"Hành động không hợp lệ: {action}")
            return "Hành động không hợp lệ. Các hành động hợp lệ: ON, OFF"
        
        # Tạo mã one-touch
        one_touch_code = f"TURN_{action}_{device_type}"
        
        # Lấy danh sách nhà từ API
        room_info = get_device_list()
        room_info = json.loads(room_info)

        # Lấy thông tin về house_id
        house_id = room_info[0]['house_id']

        headers = {
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            "Content-Type": "application/json",
            'X-Origin': 'smarthiz'
        }
        
        # Gọi API one-touch để điều khiển thiết bị
        one_touch_url = env.OXII_ROOT_API_URL + f"/api/app/house/{house_id}/one-touch/{one_touch_code}/execute"
        
        one_touch_response = requests.post(one_touch_url, headers=headers, timeout=60.0)
        one_touch_response.raise_for_status()
        
        result = one_touch_response.json()
        logger.info(f"Switch {device_type} {action} response: {result}")

        # Kiểm tra kết quả
        start_time = time.time()
        success = False
        latest_status = None
        
        while time.time() - start_time < TIME_RETRY:
            try:
                current_status = get_device_list()
                current_status = json.loads(current_status)
                latest_status = current_status
                logger.info(f"Current status: {current_status} after {time.time() - start_time} seconds")
                
                # Check if devices are in desired state
                all_devices_correct = True
                expected_status = "bật" if action == "ON" else "tắt"
                
                for room in current_status:
                    for button in room['buttons']:
                        # Kiểm tra chỉ các thiết bị thuộc loại được chỉ định
                        if button['button_type'] == device_type and button['remoteIRId'] is None:
                            if button['status'] != expected_status:
                                all_devices_correct = False
                                break
                    if not all_devices_correct:
                        break
                
                if all_devices_correct:
                    success = True
                    message = f"Tất cả thiết bị {device_type} đã được {expected_status} thành công"
                    logger.info(message)
                    return message
                
                # Wait 1 second before next check
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Lỗi khi kiểm tra trạng thái thiết bị: {str(e)}")
                time.sleep(1)
                continue
        
        if not success:
            error_message = f"Chưa thể {action.lower()} tất cả thiết bị {device_type}. Trạng thái các thiết bị hiện tai: {latest_status}"
            logger.error(error_message)
            return error_message
    
    except Exception as e:
        logger.error(f"Lỗi khi điều khiển thiết bị {device_type}: {str(e)}")
        return f"Lỗi khi điều khiển thiết bị {device_type}: {str(e)}"

def switch_on_off_controls_v2(buttonId: int, data: int):
    """Control the on/off state of a switch device with mesh network support
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        buttonId (int): ID of the button to control.
        data (int): State to set (0 for off, 1 for on).
    """

    room_info = get_device_list()
    room_info = json.loads(room_info)

    button_info = None
    for room in room_info:
        for button in room['buttons']:
            if button['buttonId'] == buttonId:
                button_info = button
                break
    if button_info is None:
        raise ValueError(f"Không tìm thấy thông tin của nút bấm với buttonId: {buttonId}")

    logger.info(f"Button info: {button_info}")

    deviceId = button_info['deviceId']
    button_code = button_info['button_code']
    logger.info(f"Switch on/off controls v2: {buttonId}, {deviceId}, {button_code}, {data}")
    
    try:
        # get serial number
        response = get_device_info(deviceId)
        logger.info(f"Device info: {response.json()}")

        if response.json()['data']['status'] == 2 and response.json()['data']['joinMesh'] == 0:
            logger.error(f"Thiết bị đang tắt, không thể điều khiển.")
            return "Thiết bị đang tắt, không thể điều khiển."
        
        serial_number = response.json()['data']['seriNumber']
        logger.info(f"Serial number: {serial_number}")
        
        # on/off device
        url = env.OXII_ROOT_API_URL + "/api/app/device/switch/on-off-controls-v2"
        payload = json.dumps({
            "serial_number": serial_number,
            "command_type": int('2'+button_code[-2:]),
            "data": data
        })
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            'X-Origin': 'smarthiz'
        }
        logger.info(f"Headers: {headers}")
        logger.info(f"Switch on/off controls v2 payload: {payload}")
        response = requests.put(url, headers=headers, data=payload, timeout=60.0)
        response.raise_for_status()
        logger.info(f"Switch on/off controls v2 response: {response.json()}")
        logger.info("-------------------------------------")
        
        # Kiểm tra kết quả
        start_time = time.time()
        success = False
        latest_status = None
        
        while time.time() - start_time < TIME_RETRY:
            try:
                current_status = get_device_list()
                current_status = json.loads(current_status)
                latest_status = current_status
                logger.info(f"Current status: {current_status} after {time.time() - start_time} seconds")
                
                # Check if the specific device is in desired state
                for room in current_status:
                    for button in room['buttons']:
                        if button['buttonId'] == buttonId:
                            button_name = button['name']
                            expected_status = "bật" if data == 1 else "tắt"
                            if button['status'] == expected_status:
                                success = True
                                message = f"Thiết bị {button_name} đã được {expected_status} thành công"
                                logger.info(message)
                                return message
                
                # Wait 1 second before next check
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Lỗi khi kiểm tra trạng thái thiết bị: {str(e)}")
                time.sleep(1)
                continue
        
        if not success:
            error_message = f"Chưa thể điều khiển thiết bị {deviceId}. Trạng thái hiện tại: {latest_status}"
            logger.error(error_message)
            return error_message

    except Exception as e:
        logger.error(f"Lỗi khi gửi lệnh điều khiển thiết bị: {str(e)}")
        raise

def room_one_touch_control(room_id: str, one_touch_code: str):
    """Execute room-level one-touch control for devices in a specific room
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        room_id (str): The ID of the room.
        one_touch_code (str): The one-touch control code. Supported codes: 
                             TURN_ON_ALL_DEVICES, TURN_OFF_ALL_DEVICES, 
                             TURN_ON_LIGHT, TURN_OFF_LIGHT, 
                             TURN_ON_FAN, TURN_OFF_FAN, 
                             TURN_ON_HOT_COLD_SHOWER, TURN_OFF_HOT_COLD_SHOWER
    
    Returns:
        str: Result of the one-touch control execution.
    """
    
    logger.info(f"Room one-touch control: room_id={room_id}, code={one_touch_code}")
    
    # Validate one-touch code
    valid_codes = [
        "TURN_ON_ALL_DEVICES", "TURN_OFF_ALL_DEVICES",
        "TURN_ON_LIGHT", "TURN_OFF_LIGHT", 
        "TURN_ON_FAN", "TURN_OFF_FAN",
        "TURN_ON_HOT_COLD_SHOWER", "TURN_OFF_HOT_COLD_SHOWER"
    ]
    
    if one_touch_code not in valid_codes:
        raise ValueError(f"Mã one-touch không hợp lệ: {one_touch_code}. Các mã hợp lệ: {', '.join(valid_codes)}")
    
    try:
        # Gọi API one-touch control
        url = env.OXII_ROOT_API_URL + f"/api/app/room/{room_id}/one-touch/{one_touch_code}/execute"
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            'X-Origin': 'smarthiz'
        }
        
        logger.info(f"Room one-touch control URL: {url}")
        logger.info(f"Headers: {headers}")
        
        response = requests.post(url, headers=headers, timeout=60.0)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Room one-touch control response: {result}")
        logger.info("-------------------------------------")
        
        # Tạo thông báo phản hồi dựa trên mã one-touch
        action_messages = {
            "TURN_ON_ALL_DEVICES": "Đã bật tất cả thiết bị trong phòng",
            "TURN_OFF_ALL_DEVICES": "Đã tắt tất cả thiết bị trong phòng",
            "TURN_ON_LIGHT": "Đã bật đèn trong phòng",
            "TURN_OFF_LIGHT": "Đã tắt đèn trong phòng",
            "TURN_ON_FAN": "Đã bật quạt trong phòng",
            "TURN_OFF_FAN": "Đã tắt quạt trong phòng",
            "TURN_ON_HOT_COLD_SHOWER": "Đã bật máy nước nóng lạnh trong phòng",
            "TURN_OFF_HOT_COLD_SHOWER": "Đã tắt máy nước nóng lạnh trong phòng"
        }
        
        return action_messages.get(one_touch_code, "Đã thực hiện lệnh one-touch thành công")
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logger.error(f"Lỗi xác thực hoặc không tìm thấy phòng: {str(e)}")
            raise ValueError("Phòng không tồn tại hoặc bạn không có quyền điều khiển thiết bị trong phòng này")
        elif e.response.status_code == 500:
            logger.error(f"Mã one-touch không hợp lệ: {str(e)}")
            raise ValueError(f"Mã one-touch không hợp lệ: {one_touch_code}")
        else:
            logger.error(f"Lỗi HTTP khi thực hiện one-touch control: {str(e)}")
            raise
    except Exception as e:
        logger.error(f"Lỗi khi thực hiện room one-touch control: {str(e)}")
        raise
