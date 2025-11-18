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
from template.api_things.info_devices import get_device_info, get_device_list

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

async def cronjob_device(deviceId: int, action: int, job_status: int, cron_time: str, button_code: str, command: str, issetting_online: bool):
    """Create or update cronjob settings for an OXII device
    Args:
        deviceId (int): ID of the device.
        action (int): Action of cronjob: 1 for add/update, 3 for delete.
        job_status (int): Job status: 0 for inactive, 1 for active.
        cron_time (str): Cron time in Cron Expression format "* * * * * *". With 6 fields respectively (second, minute, hour, day, month, day_of_week)
        button_code (str): Button code of device (button01, button02, button03, button04).
        command (str): Command to send (on, off, up, down, volume).
        issetting_online (bool): Whether to apply setting online.
    """

    logger.info(f"Cronjob device: {deviceId}, {action}, {job_status}, {cron_time}, {button_code}, {command}, {issetting_online}")
    
    # Thêm khóa để xử lý đồng thời
    device_key = f"device_{deviceId}"
    async with cache_lock:
        # Thêm trì hoãn ngẫu nhiên để tránh xung đột
        await asyncio.sleep(1)
        
        # try:
        # get cronjob setting
        cronjob, serial_number = None, None
        try:
            response = await get_device_info(deviceId)
        except ValueError as e: # Bắt lỗi từ get_device_info
            return str(e)
        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin thiết bị: {str(e)}")
            raise

        serial_number = response.json()['data']['seriNumber']
        properties = response.json()['data']['properties']
        version = response.json()['data']['hardwareVersion']

        # on/off device SH1 SH2
        if version != "4":
            url = env.OXII_ROOT_API_URL + "/api/app/device/switch/save-crontab"
            lid = int(button_code[-1])
            d = 1 if command.upper() == 'ON' else 0
            cronjob_str = [i['value'] for i in properties if i['code'] == 'f_cronjob_setting'][0]
            cronjob = json.loads(cronjob_str)
            logger.info(f"Cronjob setting: {cronjob}")

            new_sch = cronjob['sch']
            if action == 1:
                new_sch.append({
                    "e": job_status,
                    "j": cron_time,
                    "d": [
                        {
                            "lid": lid,
                            "d": d
                        }
                    ]
                })
            else:
                count = 1
                for item in cronjob['sch']:
                    if item['j'][4:] != cron_time[2:] and item['e'] == 1 and item['d'][0]['lid'] == lid and item['d'][0]['d'] == d:
                        new_sch.append({
                            "i": count,
                            "a": action,
                            "s": {
                                "e": job_status,
                                "j": cron_time, 
                                "d": [
                                    {
                                        "lid": lid,
                                        "d": d
                                    }
                                ]
                            }
                        })
                    count += 1
        
            new_jobIndex = len(new_sch)
            payload = json.dumps({
                "serial_number": serial_number,
                "command_type": 209,
                "data": {
                    "total": new_jobIndex,
                    "sch": new_sch
                }
            })
            logger.info(f"Cronjob device {deviceId} payload: {payload}")
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "Authorization": f"Bearer {env.OXII_API_KEY}",
                'X-Origin': 'smarthiz'
            }
            logger.info(f"Headers: {headers}")
            response = await http_client.post(url, headers=headers, data=payload)
            response.raise_for_status()

        # cronjob device SH4
        else:
            command_status, command_send = '', ''
            lid = int(button_code[-1])
            d = 1 if command.upper() == 'ON' else 0
            
            # Kiểm tra cache trước khi lấy từ properties
            if device_key in temp_cronjob_cache:
                logger.info(f"Sử dụng dữ liệu cronjob từ cache cho thiết bị {deviceId}")
                cronjob = temp_cronjob_cache[device_key]
            else:
                if 'ble_mesh_f_cronjob' in [i['code'] for i in properties]:
                    cronjob_str = [i['value'] for i in properties if i['code'] == 'ble_mesh_f_cronjob'][0]
                    cronjob = json.loads(cronjob_str)
                else:
                    cronjob = []
            
            logger.info(f"Cronjob setting: {cronjob}")

            for i in range(4):
                if i+1 == lid:
                    command_send = str(d) + command_send
                    command_status = '1' + command_status
                else:
                    command_send = '0' + command_send
                    command_status = '0' + command_status
            button_state = int(f'{command_status}{command_send}', 2)
            
            # get cronjob setting
            cron_struct = cron_to_custom_format(cron_time)
            if action == 1:
                # Tìm chỉ số bé nhất <= 10 chưa tôn tại trong cronjob
                for i in range(1, 11):
                    if i not in [item['i'] for item in cronjob]:
                        new_cronJobData = {
                            "i": i,
                            "a": action,
                            "s": {
                                "e": job_status,
                                "j": cron_struct['j'],
                                "w": cron_struct['w']
                            },
                            "b": button_state
                        }
                        break
                else:
                    logger.error(f"Không tìm thấy chỉ số cronjob để thêm")
                    return "Không tìm thấy chỉ số cronjob để thêm"
            else:
                count = 1
                check_cronjob = False
                new_cronJobData = None
                for item in cronjob:
                    if item['s']['j'][0] == cron_struct['j'][0] and \
                        item['s']['j'][1] == cron_struct['j'][1] and \
                        item['s']['j'][2] == cron_struct['j'][2] and \
                        item['s']['j'][3] == cron_struct['j'][3] and \
                        set(item['s']['w']) & set(cron_struct['w']) and \
                        item['b'] == button_state:
                        new_cronJobData = {
                            "i": count,
                            "a": action,
                            "s": {
                                "e": job_status,
                                "j": cron_struct['j'],
                                "w": any(i not in item['s']['w'] for i in cron_struct['w'])
                            },
                            "b": button_state
                        }
                        check_cronjob = True
                        break
                    count += 1

                if not check_cronjob:
                    logger.error(f"Không tìm thấy cronjob cần cập nhật")
                    return "Không tìm thấy lịch hẹn giờ cần cập nhật"
            
            # Cập nhật cache với dữ liệu mới
            if action == 1:
                # Tạo bản sao để tránh thao tác với cùng một đối tượng
                updated_cronjob = cronjob.copy()
                updated_cronjob.append(new_cronJobData)
                temp_cronjob_cache[device_key] = updated_cronjob

            url = env.OXII_ROOT_API_URL + f"/api/app/oxii/device/{str(deviceId)}/cronjob"
            payload = json.dumps({
                "cronJobData": new_cronJobData,
                "isSettingOnl": issetting_online
            })
            logger.info(f"Cronjob device {deviceId} payload: {payload}")
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "Authorization": f"Bearer {env.OXII_API_KEY}",
                'X-Origin': 'smarthiz'
            }
            logger.info(f"Headers: {headers}")
            response = await http_client.post(url, headers=headers, data=payload)
            response.raise_for_status()
            
            # Cập nhật cache với response mới nếu thành công
            if 'data' in response.json() and 'value' in response.json()['data']:
                try:
                    updated_value = json.loads(response.json()['data']['value'])
                    temp_cronjob_cache[device_key] = updated_value
                    logger.info(f"Cập nhật cache cronjob cho thiết bị {deviceId}")
                except json.JSONDecodeError:
                    logger.error(f"Lỗi giải mã JSON từ response")

        logger.info(f"Cronjob device {deviceId} response: {response.json()}")
        logger.info("-------------------------------------")

        return response.json()
        # except Exception as e:
        #     logger.error(f"Lỗi khi cập nhật cronjob: {str(e)}")
        #     # Xóa cache nếu có lỗi để đảm bảo lần gọi tiếp theo sẽ lấy dữ liệu mới
        #     if device_key in temp_cronjob_cache:
        #         del temp_cronjob_cache[device_key]
        #     raise

async def cronjob_device_v2(buttonId: int, action: int, job_status: int, cron_time: str, button_code: str, command: str, issetting_online: bool):
    """Create or update cronjob settings for an OXII device
    Args:
        env.OXII_API_KEY (str): env.OXII_API_KEY authentication from Oxii API.
        buttonId (int): ID of the remotebutton.
        action (int): Action of cronjob: 1 for add/update, 3 for delete.
        job_status (int): Job status: 0 for inactive, 1 for active.
        cron_time (str): Cron time in Cron Expression format "* * * * * *". With 6 fields respectively (second, minute, hour, day, month, day_of_week)
        button_code (str): Button code of device (button01, button02, button03, button04).
        command (str): Command to send (on, off, up, down, volume).
        issetting_online (bool): Whether to apply setting online.
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

    deviceId = button_info['deviceId']
    logger.info(f"Cronjob device: {deviceId}, {action}, {job_status}, {cron_time}, {button_code}, {command}, {issetting_online}")
    
    # Thêm khóa để xử lý đồng thời
    device_key = f"device_{deviceId}"
    async with cache_lock:
        # Thêm trì hoãn ngẫu nhiên để tránh xung đột
        await asyncio.sleep(1)
        
        # try:
        # get cronjob setting
        cronjob, serial_number = None, None
        try:
            response = await get_device_info(env.OXII_API_KEY, deviceId)
        except ValueError as e: # Bắt lỗi từ get_device_info
            return str(e)
        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin thiết bị: {str(e)}")
            raise

        serial_number = response.json()['data']['seriNumber']
        properties = response.json()['data']['properties']
        version = response.json()['data']['hardwareVersion']

        # on/off device SH1 SH2
        if version != "4":
            url = env.OXII_ROOT_API_URL + "/api/app/device/switch/save-crontab"
            lid = int(button_code[-1])
            d = 1 if command.upper() == 'ON' else 0
            cronjob_str = [i['value'] for i in properties if i['code'] == 'f_cronjob_setting'][0]
            cronjob = json.loads(cronjob_str)
            logger.info(f"Cronjob setting: {cronjob}")

            new_sch = cronjob['sch']
            if action == 1:
                new_sch.append({
                    "e": job_status,
                    "j": cron_time,
                    "d": [
                        {
                            "lid": lid,
                            "d": d
                        }
                    ]
                })
            else:
                count = 1
                for item in cronjob['sch']:
                    if item['j'][4:] != cron_time[2:] and item['e'] == 1 and item['d'][0]['lid'] == lid and item['d'][0]['d'] == d:
                        new_sch.append({
                            "i": count,
                            "a": action,
                            "s": {
                                "e": job_status,
                                "j": cron_time, 
                                "d": [
                                    {
                                        "lid": lid,
                                        "d": d
                                    }
                                ]
                            }
                        })
                    count += 1
        
            new_jobIndex = len(new_sch)
            payload = json.dumps({
                "serial_number": serial_number,
                "command_type": 209,
                "data": {
                    "total": new_jobIndex,
                    "sch": new_sch
                }
            })
            logger.info(f"Cronjob device {deviceId} payload: {payload}")
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "Authorization": f"Bearer {env.OXII_API_KEY}",
                'X-Origin': 'smarthiz'
            }
            logger.info(f"Headers: {headers}")
            response = await http_client.post(url, headers=headers, data=payload)
            response.raise_for_status()

        # cronjob device SH4
        else:
            command_status, command_send = '', ''
            lid = int(button_code[-1])
            d = 1 if command.upper() == 'ON' else 0
            
            # Kiểm tra cache trước khi lấy từ properties
            if device_key in temp_cronjob_cache:
                logger.info(f"Sử dụng dữ liệu cronjob từ cache cho thiết bị {deviceId}")
                cronjob = temp_cronjob_cache[device_key]
            else:
                if 'ble_mesh_f_cronjob' in [i['code'] for i in properties]:
                    cronjob_str = [i['value'] for i in properties if i['code'] == 'ble_mesh_f_cronjob'][0]
                    cronjob = json.loads(cronjob_str)
                else:
                    cronjob = []
            
            logger.info(f"Cronjob setting: {cronjob}")

            for i in range(4):
                if i+1 == lid:
                    command_send = str(d) + command_send
                    command_status = '1' + command_status
                else:
                    command_send = '0' + command_send
                    command_status = '0' + command_status
            button_state = int(f'{command_status}{command_send}', 2)
            
            # get cronjob setting
            cron_struct = cron_to_custom_format(cron_time)
            if action == 1:
                # Tìm chỉ số bé nhất <= 10 chưa tôn tại trong cronjob
                for i in range(1, 11):
                    if i not in [item['i'] for item in cronjob]:
                        new_cronJobData = {
                            "i": i,
                            "a": action,
                            "s": {
                                "e": job_status,
                                "j": cron_struct['j'],
                                "w": cron_struct['w']
                            },
                            "b": button_state
                        }
                        break
                else:
                    logger.error(f"Không tìm thấy chỉ số cronjob để thêm")
                    return "Không tìm thấy chỉ số cronjob để thêm"
            else:
                count = 1
                check_cronjob = False
                new_cronJobData = None
                for item in cronjob:
                    if item['s']['j'][0] == cron_struct['j'][0] and \
                        item['s']['j'][1] == cron_struct['j'][1] and \
                        item['s']['j'][2] == cron_struct['j'][2] and \
                        item['s']['j'][3] == cron_struct['j'][3] and \
                        set(item['s']['w']) & set(cron_struct['w']) and \
                        item['b'] == button_state:
                        new_cronJobData = {
                            "i": count,
                            "a": action,
                            "s": {
                                "e": job_status,
                                "j": cron_struct['j'],
                                "w": any(i not in item['s']['w'] for i in cron_struct['w'])
                            },
                            "b": button_state
                        }
                        check_cronjob = True
                        break
                    count += 1

                if not check_cronjob:
                    logger.error(f"Không tìm thấy cronjob cần cập nhật")
                    return "Không tìm thấy lịch hẹn giờ cần cập nhật"
            
            # Cập nhật cache với dữ liệu mới
            if action == 1:
                # Tạo bản sao để tránh thao tác với cùng một đối tượng
                updated_cronjob = cronjob.copy()
                updated_cronjob.append(new_cronJobData)
                temp_cronjob_cache[device_key] = updated_cronjob

            url = env.OXII_ROOT_API_URL + f"/api/app/oxii/device/{str(deviceId)}/cronjob"
            payload = json.dumps({
                "cronJobData": new_cronJobData,
                "isSettingOnl": issetting_online
            })
            logger.info(f"Cronjob device {deviceId} payload: {payload}")
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "Authorization": f"Bearer {env.OXII_API_KEY}",
                'X-Origin': 'smarthiz'
            }
            logger.info(f"Headers: {headers}")
            response = await http_client.post(url, headers=headers, data=payload)
            response.raise_for_status()
            
            # Cập nhật cache với response mới nếu thành công
            if 'data' in response.json() and 'value' in response.json()['data']:
                try:
                    updated_value = json.loads(response.json()['data']['value'])
                    temp_cronjob_cache[device_key] = updated_value
                    logger.info(f"Cập nhật cache cronjob cho thiết bị {deviceId}")
                except json.JSONDecodeError:
                    logger.error(f"Lỗi giải mã JSON từ response")

        logger.info(f"Cronjob device {deviceId} response: {response.json()}")
        logger.info("-------------------------------------")

        return response.json()
        # except Exception as e:
        #     logger.error(f"Lỗi khi cập nhật cronjob: {str(e)}")
        #     # Xóa cache nếu có lỗi để đảm bảo lần gọi tiếp theo sẽ lấy dữ liệu mới
        #     if device_key in temp_cronjob_cache:
        #         del temp_cronjob_cache[device_key]
        #     raise
