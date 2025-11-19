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

def retrieve_ir_data(label: str, brandId: int, modelName: str):
    """Retrieve IR data template and models for remote button based on device type and brand
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        label (str): Type of device (TV, CONDITIONER, FAN).
        brandId (int): ID of the device brand.
        modelName (str): Name of the device model.
    """

    logger.info(f"Retrieve IR data: {label}, {brandId}, {modelName}")
    try:
        # on/off device
        url = env.OXII_ROOT_API_URL + "/api/app/remote-button/data-ir"
        payload = {
            "label": label,
            "brandId": brandId,
            "modelName": modelName
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            'X-Origin': 'smarthiz'
        }
        logger.info(f"Retrieve IR data payload: {payload}")
        response = requests.get(url, headers=headers, params=payload, timeout=60.0)
        response.raise_for_status()
        logger.info(f"Retrieve IR data response: {response.json()}")
        logger.info("-------------------------------------")
        return response.json()
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu IR: {str(e)}")
        raise

def retrieve_ir_data_v2(buttonId: int):
    """Retrieve IR data template and models for remote button based on device type and brand
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        buttonId (int): ID of the remote button.
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

    label = button_info['label']
    brandId = button_info['brandId']
    modelName = button_info['modelName']
    logger.info(f"Retrieve IR data: {buttonId}, {label}, {brandId}, {modelName}")

    try:
        # on/off device
        url = env.OXII_ROOT_API_URL + "/api/app/remote-button/data-ir"
        payload = {
            "label": label,
            "brandId": brandId,
            "modelName": modelName
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            'X-Origin': 'smarthiz'
        }
        logger.info(f"Retrieve IR data payload: {payload}")
        response = requests.get(url, headers=headers, params=payload, timeout=60.0)
        response.raise_for_status()
        logger.info(f"Retrieve IR data response: {response.json()}")
        logger.info("-------------------------------------")
        return response.json()
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu IR: {str(e)}")
        raise

def open_ir_send_for_testing_mesh(serial_numbers: List[str], net_index: int, app_index: int, label: str, brandId: int, modelName: str, label_code: str, command_type: int=212):
    """Send IR command to devices in mesh network for TV, FAN devices, not for CONDITIONER devices
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        serial_numbers (List[str]): Serial numbers of the devices remoteButton.device.seriNumber.
        net_index (int): Network index for mesh network (house_id).
        app_index (int): Application index for mesh network (thường là 0).
        label (str): Type of device (TV, CONDITIONER, FAN).
        brandId (int): ID of the device brand.
        modelName (str): Name of the device model.
        label_code (str): The code of the label (e.g., "KEY_POWER").
        command_type (int): Command type for IR send (default is 212 for TV/Fan)
    """

    logger.info(f"Open IR send for testing mesh: {serial_numbers}, {net_index}, {app_index}, {label}, {brandId}, {modelName}, {label_code}")
    try:
        ir_data_response = retrieve_ir_data(label, brandId, modelName)
        ir_data_template = ir_data_response['data']['remoteDataIR']['template']
        
        data = None
        for item in ir_data_template:
            if item['code'] == label_code:
                data = {
                    "Data": item['value'],
                    "Bits": item['bits'],
                    "Protocol": item['protocol'],
                    "Repeat": item['repeat']
                }
                break
        
        if data is None:
            raise ValueError(f"Không tìm thấy dữ liệu IR cho label_code: {label_code}")
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu IR: {str(e)}")
        raise
    
    try:
        # Chuẩn bị payload theo đúng định dạng API
        url = env.OXII_ROOT_API_URL + "/api/app/device/switch/open-ir-send-for-testing-mesh"
        payload = {
            "serial_number": serial_numbers,
            "command_type": command_type,
            "meshIndex": {
                "net_Index": net_index,
                "app_Index": app_index
            },
            "data": data
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            'X-Origin': 'smarthiz'
        }

        logger.info(f"Open IR send for testing mesh payload: {payload}")
        response = requests.post(url, headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        logger.info(f"Open IR send for testing mesh response: {response.json()}")
        logger.info("-------------------------------------")
        return "Đã gửi lệnh IR thành công"
    except ValueError as ve:
        logger.error(f"Lỗi dữ liệu IR: {str(ve)}")
        raise
    except Exception as e:
        logger.error(f"Lỗi khi gửi lệnh IR: {str(e)}")
        raise

def open_ir_send_for_testing_mesh_v2(buttonId: int, templateID: int):
    """Send IR command to devices in mesh network for TV, FAN devices, not for CONDITIONER devices
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        buttonId (int): ID of the remote button.
        templateID (int): The ID of the control template.
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

    label = button_info['label']
    brandId = button_info['brandId']
    modelName = button_info['modelName']
    serial_numbers = [button_info['seriNumber']]
    net_index = button_info['net_Index']
    app_index = button_info['app_Index']
    command_type = 212 # Default for TV/Fan

    logger.info(f"Open IR send for testing mesh: {buttonId}, {serial_numbers}, {net_index}, {app_index}, {label}, {brandId}, {modelName}")
    try:
        ir_data_response = retrieve_ir_data(label, brandId, modelName)
        ir_data_template = ir_data_response['data']['remoteDataIR']['template']
        
        data = None
        for item in ir_data_template:
            if item['id'] == templateID:
                data = {
                    "Data": item['value'],
                    "Bits": item['bits'],
                    "Protocol": item['protocol'],
                    "Repeat": item['repeat']
                }
                break
        
        if data is None:
            raise ValueError(f"Không tìm thấy dữ liệu IR cho templateID: {templateID}")
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu IR: {str(e)}")
        raise
    
    try:
        # Chuẩn bị payload theo đúng định dạng API
        url = env.OXII_ROOT_API_URL + "/api/app/device/switch/open-ir-send-for-testing-mesh"
        payload = {
            "serial_number": serial_numbers,
            "command_type": command_type,
            "meshIndex": {
                "net_Index": net_index,
                "app_Index": app_index
            },
            "data": data
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {env.OXII_API_KEY}",
            'X-Origin': 'smarthiz'
        }

        logger.info(f"Open IR send for testing mesh payload: {payload}")
        response = requests.post(url, headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        logger.info(f"Open IR send for testing mesh response: {response.json()}")
        logger.info("-------------------------------------")
        return "Đã gửi lệnh IR thành công"
    except ValueError as ve:
        logger.error(f"Lỗi dữ liệu IR: {str(ve)}")
        raise
    except Exception as e:
        logger.error(f"Lỗi khi gửi lệnh IR: {str(e)}")
        raise
