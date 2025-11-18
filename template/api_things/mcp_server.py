from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings
import httpx
import json
from typing import List
from modules.utils.slogger import SLOG
from modules.utils.common import cron_to_custom_format
from dotenv import load_dotenv
import asyncio
import time
import os


# Load environment variables
load_dotenv(override=True)

# Create an MCP server
mcp = FastMCP(os.getenv("MCP_SERVER_NAME"))

# Tạo một client HTTP để tái sử dụng
http_client = httpx.AsyncClient(timeout=60.0)

# Biến lưu trữ cronjob tạm thời để xử lý các tác vụ đồng thời
temp_cronjob_cache = {}

# Khóa để đảm bảo chỉ một tác vụ truy cập vào cache tại một thời điểm
cache_lock = asyncio.Lock()

TIME_RETRY = 30

@mcp.tool()
async def get_device_list(token: str):
    """
    Get status of devices in the house from Oxii API.
    Args:
        token (str): Token authentication from Oxii API.

    Returns:
        str: List of devices in the house.
    """
    
    SLOG.info(f"Get device list with token: {token}")

    try:
        api_url = os.getenv("OXII_ROOT_API_URL") + "/api/app/oxii/home"
        headers = {
            "Content-Type": "application/json",
            'X-Origin': 'smarthiz',
            'Authorization': f"Bearer {token}"
        }
        payload = {"query":" ","variables":{}}
        SLOG.info(f"Headers: {headers}")
        response = await http_client.get(api_url, headers=headers, params=payload)
        response.raise_for_status()
        
        formatted_devices = []
        data = response.json()['data']
        homes = data.get('data', [])
        home = homes[0] if homes else None
        if not home:
            SLOG.error("Không tìm thấy thông tin nhà")
            return "Không tìm thấy thông tin nhà"

        # SLOG.info(f"House info: {home}")
        
        for room in home.get('rooms', []):
            room_info = {
                'house_id': home['id'],
                'room_id': room['id'],
                'room_name': room['name'],
                'devices': [],
                'buttons': []
            }

            # SLOG.info(f"Room info: {room}")

            for device in room.get('devices', []):
                device_info = {
                    'name': device['models']['displayName'],
                    'seriNumber': device['seriNumber'],
                    'device_status': 'Không thể kết nối' if device['status'] == 2 and device['joinMesh'] == 0 else "Đang kết nối"
                }
                room_info['devices'].append(device_info)
            
            # SLOG.info(f"Devices info: {room_info['devices']}")
            
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
            SLOG.info(f"Room info: {room_info}")
            SLOG.info("-------------------------------------")
        return json.dumps(formatted_devices, indent=4, ensure_ascii=False)
    except Exception as e:
        SLOG.error(f"Lỗi khi lấy danh sách thiết bị: {str(e)} với token: {token}")
        raise

async def get_device_info(token: str, deviceId: int):
    url = os.getenv("OXII_ROOT_API_URL") + f"/api/app/oxii/device/{str(deviceId)}/properties"
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json',
        "Authorization": f"Bearer {token}",
        'X-Origin': 'smarthiz'
    }
    
    response = await http_client.get(url, headers=headers)
    response.raise_for_status()

    return response

@mcp.tool()
async def cronjob_device(token: str, deviceId: int, action: int, job_status: int, cron_time: str, button_code: str, command: str, issetting_online: bool):
    """Create or update cronjob settings for an OXII device
    Args:
        token (str): Token authentication from Oxii API.
        deviceId (int): ID of the device.
        action (int): Action of cronjob: 1 for add/update, 3 for delete.
        job_status (int): Job status: 0 for inactive, 1 for active.
        cron_time (str): Cron time in Cron Expression format "* * * * * *". With 6 fields respectively (second, minute, hour, day, month, day_of_week)
        button_code (str): Button code of device (button01, button02, button03, button04).
        command (str): Command to send (on, off, up, down, volume).
        issetting_online (bool): Whether to apply setting online.
    """

    SLOG.info(f"Cronjob device: {deviceId}, {action}, {job_status}, {cron_time}, {button_code}, {command}, {issetting_online}")
    
    # Thêm khóa để xử lý đồng thời
    device_key = f"device_{deviceId}"
    async with cache_lock:
        # Thêm trì hoãn ngẫu nhiên để tránh xung đột
        await asyncio.sleep(1)
        
        # try:
        # get cronjob setting
        cronjob, serial_number = None, None
        try:
            response = await get_device_info(token, deviceId)
        except ValueError as e: # Bắt lỗi từ get_device_info
            return str(e)
        except Exception as e:
            SLOG.error(f"Lỗi khi lấy thông tin thiết bị: {str(e)}")
            raise

        serial_number = response.json()['data']['seriNumber']
        properties = response.json()['data']['properties']
        version = response.json()['data']['hardwareVersion']

        # on/off device SH1 SH2
        if version != "4":
            url = os.getenv("OXII_ROOT_API_URL") + "/api/app/device/switch/save-crontab"
            lid = int(button_code[-1])
            d = 1 if command.upper() == 'ON' else 0
            cronjob_str = [i['value'] for i in properties if i['code'] == 'f_cronjob_setting'][0]
            cronjob = json.loads(cronjob_str)
            SLOG.info(f"Cronjob setting: {cronjob}")

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
            SLOG.info(f"Cronjob device {deviceId} payload: {payload}")
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "Authorization": f"Bearer {token}",
                'X-Origin': 'smarthiz'
            }
            SLOG.info(f"Headers: {headers}")
            response = await http_client.post(url, headers=headers, data=payload)
            response.raise_for_status()

        # cronjob device SH4
        else:
            command_status, command_send = '', ''
            lid = int(button_code[-1])
            d = 1 if command.upper() == 'ON' else 0
            
            # Kiểm tra cache trước khi lấy từ properties
            if device_key in temp_cronjob_cache:
                SLOG.info(f"Sử dụng dữ liệu cronjob từ cache cho thiết bị {deviceId}")
                cronjob = temp_cronjob_cache[device_key]
            else:
                if 'ble_mesh_f_cronjob' in [i['code'] for i in properties]:
                    cronjob_str = [i['value'] for i in properties if i['code'] == 'ble_mesh_f_cronjob'][0]
                    cronjob = json.loads(cronjob_str)
                else:
                    cronjob = []
            
            SLOG.info(f"Cronjob setting: {cronjob}")

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
                    SLOG.error(f"Không tìm thấy chỉ số cronjob để thêm")
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
                    SLOG.error(f"Không tìm thấy cronjob cần cập nhật")
                    return "Không tìm thấy lịch hẹn giờ cần cập nhật"
            
            # Cập nhật cache với dữ liệu mới
            if action == 1:
                # Tạo bản sao để tránh thao tác với cùng một đối tượng
                updated_cronjob = cronjob.copy()
                updated_cronjob.append(new_cronJobData)
                temp_cronjob_cache[device_key] = updated_cronjob

            url = os.getenv("OXII_ROOT_API_URL") + f"/api/app/oxii/device/{str(deviceId)}/cronjob"
            payload = json.dumps({
                "cronJobData": new_cronJobData,
                "isSettingOnl": issetting_online
            })
            SLOG.info(f"Cronjob device {deviceId} payload: {payload}")
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "Authorization": f"Bearer {token}",
                'X-Origin': 'smarthiz'
            }
            SLOG.info(f"Headers: {headers}")
            response = await http_client.post(url, headers=headers, data=payload)
            response.raise_for_status()
            
            # Cập nhật cache với response mới nếu thành công
            if 'data' in response.json() and 'value' in response.json()['data']:
                try:
                    updated_value = json.loads(response.json()['data']['value'])
                    temp_cronjob_cache[device_key] = updated_value
                    SLOG.info(f"Cập nhật cache cronjob cho thiết bị {deviceId}")
                except json.JSONDecodeError:
                    SLOG.error(f"Lỗi giải mã JSON từ response")

        SLOG.info(f"Cronjob device {deviceId} response: {response.json()}")
        SLOG.info("-------------------------------------")

        return response.json()
        # except Exception as e:
        #     SLOG.error(f"Lỗi khi cập nhật cronjob: {str(e)}")
        #     # Xóa cache nếu có lỗi để đảm bảo lần gọi tiếp theo sẽ lấy dữ liệu mới
        #     if device_key in temp_cronjob_cache:
        #         del temp_cronjob_cache[device_key]
        #     raise

@mcp.tool()
async def cronjob_device_v2(token: str, buttonId: int, action: int, job_status: int, cron_time: str, button_code: str, command: str, issetting_online: bool):
    """Create or update cronjob settings for an OXII device
    Args:
        token (str): Token authentication from Oxii API.
        buttonId (int): ID of the remotebutton.
        action (int): Action of cronjob: 1 for add/update, 3 for delete.
        job_status (int): Job status: 0 for inactive, 1 for active.
        cron_time (str): Cron time in Cron Expression format "* * * * * *". With 6 fields respectively (second, minute, hour, day, month, day_of_week)
        button_code (str): Button code of device (button01, button02, button03, button04).
        command (str): Command to send (on, off, up, down, volume).
        issetting_online (bool): Whether to apply setting online.
    """

    room_info = await get_device_list(token)
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
    SLOG.info(f"Cronjob device: {deviceId}, {action}, {job_status}, {cron_time}, {button_code}, {command}, {issetting_online}")
    
    # Thêm khóa để xử lý đồng thời
    device_key = f"device_{deviceId}"
    async with cache_lock:
        # Thêm trì hoãn ngẫu nhiên để tránh xung đột
        await asyncio.sleep(1)
        
        # try:
        # get cronjob setting
        cronjob, serial_number = None, None
        try:
            response = await get_device_info(token, deviceId)
        except ValueError as e: # Bắt lỗi từ get_device_info
            return str(e)
        except Exception as e:
            SLOG.error(f"Lỗi khi lấy thông tin thiết bị: {str(e)}")
            raise

        serial_number = response.json()['data']['seriNumber']
        properties = response.json()['data']['properties']
        version = response.json()['data']['hardwareVersion']

        # on/off device SH1 SH2
        if version != "4":
            url = os.getenv("OXII_ROOT_API_URL") + "/api/app/device/switch/save-crontab"
            lid = int(button_code[-1])
            d = 1 if command.upper() == 'ON' else 0
            cronjob_str = [i['value'] for i in properties if i['code'] == 'f_cronjob_setting'][0]
            cronjob = json.loads(cronjob_str)
            SLOG.info(f"Cronjob setting: {cronjob}")

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
            SLOG.info(f"Cronjob device {deviceId} payload: {payload}")
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "Authorization": f"Bearer {token}",
                'X-Origin': 'smarthiz'
            }
            SLOG.info(f"Headers: {headers}")
            response = await http_client.post(url, headers=headers, data=payload)
            response.raise_for_status()

        # cronjob device SH4
        else:
            command_status, command_send = '', ''
            lid = int(button_code[-1])
            d = 1 if command.upper() == 'ON' else 0
            
            # Kiểm tra cache trước khi lấy từ properties
            if device_key in temp_cronjob_cache:
                SLOG.info(f"Sử dụng dữ liệu cronjob từ cache cho thiết bị {deviceId}")
                cronjob = temp_cronjob_cache[device_key]
            else:
                if 'ble_mesh_f_cronjob' in [i['code'] for i in properties]:
                    cronjob_str = [i['value'] for i in properties if i['code'] == 'ble_mesh_f_cronjob'][0]
                    cronjob = json.loads(cronjob_str)
                else:
                    cronjob = []
            
            SLOG.info(f"Cronjob setting: {cronjob}")

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
                    SLOG.error(f"Không tìm thấy chỉ số cronjob để thêm")
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
                    SLOG.error(f"Không tìm thấy cronjob cần cập nhật")
                    return "Không tìm thấy lịch hẹn giờ cần cập nhật"
            
            # Cập nhật cache với dữ liệu mới
            if action == 1:
                # Tạo bản sao để tránh thao tác với cùng một đối tượng
                updated_cronjob = cronjob.copy()
                updated_cronjob.append(new_cronJobData)
                temp_cronjob_cache[device_key] = updated_cronjob

            url = os.getenv("OXII_ROOT_API_URL") + f"/api/app/oxii/device/{str(deviceId)}/cronjob"
            payload = json.dumps({
                "cronJobData": new_cronJobData,
                "isSettingOnl": issetting_online
            })
            SLOG.info(f"Cronjob device {deviceId} payload: {payload}")
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json',
                "Authorization": f"Bearer {token}",
                'X-Origin': 'smarthiz'
            }
            SLOG.info(f"Headers: {headers}")
            response = await http_client.post(url, headers=headers, data=payload)
            response.raise_for_status()
            
            # Cập nhật cache với response mới nếu thành công
            if 'data' in response.json() and 'value' in response.json()['data']:
                try:
                    updated_value = json.loads(response.json()['data']['value'])
                    temp_cronjob_cache[device_key] = updated_value
                    SLOG.info(f"Cập nhật cache cronjob cho thiết bị {deviceId}")
                except json.JSONDecodeError:
                    SLOG.error(f"Lỗi giải mã JSON từ response")

        SLOG.info(f"Cronjob device {deviceId} response: {response.json()}")
        SLOG.info("-------------------------------------")

        return response.json()
        # except Exception as e:
        #     SLOG.error(f"Lỗi khi cập nhật cronjob: {str(e)}")
        #     # Xóa cache nếu có lỗi để đảm bảo lần gọi tiếp theo sẽ lấy dữ liệu mới
        #     if device_key in temp_cronjob_cache:
        #         del temp_cronjob_cache[device_key]
        #     raise

@mcp.tool()
async def switch_on_off_all_device(token: str, command: str):
    """Turn on off all devices in a house using one-touch control
    Args:
        token (str): Token authentication from Oxii API.
        command (str): Command to send (on, off).
    """
    SLOG.info(f"Switch on all device with token: {token}")
    try:
        room_info = await get_device_list(token)
        room_info = json.loads(room_info)

        # Lấy thông tin về house_id
        house_id = room_info[0]['house_id']

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            'X-Origin': 'smarthiz'
        }
        
        # Gọi API one-touch để bật tất cả thiết bị
        if command.upper() == 'OFF':
            one_touch_url = os.getenv("OXII_ROOT_API_URL") + f"/api/app/house/{house_id}/one-touch/TURN_OFF_ALL_DEVICES/execute"
            text_command = "tắt"
        else:
            one_touch_url = os.getenv("OXII_ROOT_API_URL") + f"/api/app/house/{house_id}/one-touch/TURN_ON_ALL_DEVICES/execute"
            text_command = "bật"
        
        one_touch_response = await http_client.post(one_touch_url, headers=headers)
        one_touch_response.raise_for_status()
        
        result = one_touch_response.json()
        SLOG.info(f"Switch all device response: {result}")
        
        # Kiểm tra kết quả
        start_time = time.time()
        success = False
        latest_status = None
        
        while time.time() - start_time < TIME_RETRY:
            try:
                current_status = await get_device_list(token)
                current_status = json.loads(current_status)
                latest_status = current_status
                SLOG.info(f"Current status: {current_status} after {time.time() - start_time} seconds")
                
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
                    SLOG.info(f"Tất cả thiết bị đã được {text_command} thành công")
                    return f"Tất cả thiết bị đã được {text_command} thành công"
                
                # Wait 1 second before next check
                await asyncio.sleep(1)
                
            except Exception as e:
                SLOG.error(f"Lỗi khi kiểm tra trạng thái thiết bị: {str(e)}")
                await asyncio.sleep(1)
                continue
        
        if not success:
            SLOG.error(f"Chưa thể bật tất cả thiết bị. Trạng thái các thiết bị hiện tai: {latest_status}")
            return f"Chưa thể bật tất cả thiết bị. Trạng thái các thiết bị hiện tai: {latest_status}"
    
    except Exception as e:
        SLOG.error(f"Lỗi khi bật tất cả thiết bị: {str(e)}")
        return f"Lỗi khi bật tất cả thiết bị: {str(e)}"

@mcp.tool()
async def switch_device_by_type(token: str, device_type: str, action: str):
    """Turn on/off devices by type using one-touch control
    Args:
        token (str): Token authentication from Oxii API.
        device_type (str): Type of device (LIGHT, TV, CONDITIONER, FAN, HOT_COLD_SHOWER, SOCKET).
        action (str): Action to perform (ON, OFF).
    """
    SLOG.info(f"Switch {device_type} {action} with token: {token}")
    try:
        # Kiểm tra tham số đầu vào
        device_type = device_type.upper()
        action = action.upper()
        
        # Kiểm tra loại thiết bị hợp lệ
        valid_device_types = ["LIGHT", "TV", "CONDITIONER", "FAN", "HOT_COLD_SHOWER", "SOCKET"]
        if device_type not in valid_device_types:
            SLOG.error(f"Loại thiết bị không hợp lệ: {device_type}")
            return f"Loại thiết bị không hợp lệ. Các loại hợp lệ: {', '.join(valid_device_types)}"
        
        # Kiểm tra hành động hợp lệ
        if action not in ["ON", "OFF"]:
            SLOG.error(f"Hành động không hợp lệ: {action}")
            return "Hành động không hợp lệ. Các hành động hợp lệ: ON, OFF"
        
        # Tạo mã one-touch
        one_touch_code = f"TURN_{action}_{device_type}"
        
        # Lấy danh sách nhà từ API
        room_info = await get_device_list(token)
        room_info = json.loads(room_info)

        # Lấy thông tin về house_id
        house_id = room_info[0]['house_id']

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            'X-Origin': 'smarthiz'
        }
        
        # Gọi API one-touch để điều khiển thiết bị
        one_touch_url = os.getenv("OXII_ROOT_API_URL") + f"/api/app/house/{house_id}/one-touch/{one_touch_code}/execute"
        
        one_touch_response = await http_client.post(one_touch_url, headers=headers)
        one_touch_response.raise_for_status()
        
        result = one_touch_response.json()
        SLOG.info(f"Switch {device_type} {action} response: {result}")

        # Kiểm tra kết quả
        start_time = time.time()
        success = False
        latest_status = None
        
        while time.time() - start_time < TIME_RETRY:
            try:
                current_status = await get_device_list(token)
                current_status = json.loads(current_status)
                latest_status = current_status
                SLOG.info(f"Current status: {current_status} after {time.time() - start_time} seconds")
                
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
                    SLOG.info(message)
                    return message
                
                # Wait 1 second before next check
                await asyncio.sleep(1)
                
            except Exception as e:
                SLOG.error(f"Lỗi khi kiểm tra trạng thái thiết bị: {str(e)}")
                await asyncio.sleep(1)
                continue
        
        if not success:
            error_message = f"Chưa thể {action.lower()} tất cả thiết bị {device_type}. Trạng thái các thiết bị hiện tai: {latest_status}"
            SLOG.error(error_message)
            return error_message
    
    except Exception as e:
        SLOG.error(f"Lỗi khi điều khiển thiết bị {device_type}: {str(e)}")
        return f"Lỗi khi điều khiển thiết bị {device_type}: {str(e)}"

@mcp.tool()
async def switch_on_off_controls_v2(token: str, buttonId: int, data: int):
    """Control the on/off state of a switch device with mesh network support
    Args:
        token (str): Token authentication from Oxii API.
        buttonId (int): ID of the button to control.
        data (int): State to set (0 for off, 1 for on).
    """

    room_info = await get_device_list(token)
    room_info = json.loads(room_info)

    button_info = None
    for room in room_info:
        for button in room['buttons']:
            if button['buttonId'] == buttonId:
                button_info = button
                break
    if button_info is None:
        raise ValueError(f"Không tìm thấy thông tin của nút bấm với buttonId: {buttonId}")

    SLOG.info(f"Button info: {button_info}")

    deviceId = button_info['deviceId']
    button_code = button_info['button_code']
    SLOG.info(f"Switch on/off controls v2: {buttonId}, {deviceId}, {button_code}, {data}")
    
    try:
        # get serial number
        response = await get_device_info(token, deviceId)
        SLOG.info(f"Device info: {response.json()}")

        if response.json()['data']['status'] == 2 and response.json()['data']['joinMesh'] == 0:
            SLOG.error(f"Thiết bị đang tắt, không thể điều khiển.")
            return "Thiết bị đang tắt, không thể điều khiển."
        
        serial_number = response.json()['data']['seriNumber']
        SLOG.info(f"Serial number: {serial_number}")
        
        # on/off device
        url = os.getenv("OXII_ROOT_API_URL") + "/api/app/device/switch/on-off-controls-v2"
        payload = json.dumps({
            "serial_number": serial_number,
            "command_type": int('2'+button_code[-2:]),
            "data": data
        })
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {token}",
            'X-Origin': 'smarthiz'
        }
        SLOG.info(f"Headers: {headers}")
        SLOG.info(f"Switch on/off controls v2 payload: {payload}")
        response = await http_client.put(url, headers=headers, data=payload)
        response.raise_for_status()
        SLOG.info(f"Switch on/off controls v2 response: {response.json()}")
        SLOG.info("-------------------------------------")
        
        # Kiểm tra kết quả
        start_time = time.time()
        success = False
        latest_status = None
        
        while time.time() - start_time < TIME_RETRY:
            try:
                current_status = await get_device_list(token)
                current_status = json.loads(current_status)
                latest_status = current_status
                SLOG.info(f"Current status: {current_status} after {time.time() - start_time} seconds")
                
                # Check if the specific device is in desired state
                for room in current_status:
                    for button in room['buttons']:
                        if button['buttonId'] == buttonId:
                            button_name = button['name']
                            expected_status = "bật" if data == 1 else "tắt"
                            if button['status'] == expected_status:
                                success = True
                                message = f"Thiết bị {button_name} đã được {expected_status} thành công"
                                SLOG.info(message)
                                return message
                
                # Wait 1 second before next check
                await asyncio.sleep(1)
                
            except Exception as e:
                SLOG.error(f"Lỗi khi kiểm tra trạng thái thiết bị: {str(e)}")
                await asyncio.sleep(1)
                continue
        
        if not success:
            error_message = f"Chưa thể điều khiển thiết bị {deviceId}. Trạng thái hiện tại: {latest_status}"
            SLOG.error(error_message)
            return error_message

    except Exception as e:
        SLOG.error(f"Lỗi khi gửi lệnh điều khiển thiết bị: {str(e)}")
        raise

@mcp.tool()
async def room_one_touch_control(token: str, room_id: str, one_touch_code: str):
    """Execute room-level one-touch control for devices in a specific room
    Args:
        token (str): Token authentication from Oxii API.
        room_id (str): The ID of the room.
        one_touch_code (str): The one-touch control code. Supported codes: 
                             TURN_ON_ALL_DEVICES, TURN_OFF_ALL_DEVICES, 
                             TURN_ON_LIGHT, TURN_OFF_LIGHT, 
                             TURN_ON_FAN, TURN_OFF_FAN, 
                             TURN_ON_HOT_COLD_SHOWER, TURN_OFF_HOT_COLD_SHOWER
    
    Returns:
        str: Result of the one-touch control execution.
    """
    
    SLOG.info(f"Room one-touch control: room_id={room_id}, code={one_touch_code}")
    
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
        url = os.getenv("OXII_ROOT_API_URL") + f"/api/app/room/{room_id}/one-touch/{one_touch_code}/execute"
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {token}",
            'X-Origin': 'smarthiz'
        }
        
        SLOG.info(f"Room one-touch control URL: {url}")
        SLOG.info(f"Headers: {headers}")
        
        response = await http_client.post(url, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        SLOG.info(f"Room one-touch control response: {result}")
        SLOG.info("-------------------------------------")
        
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
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            SLOG.error(f"Lỗi xác thực hoặc không tìm thấy phòng: {str(e)}")
            raise ValueError("Phòng không tồn tại hoặc bạn không có quyền điều khiển thiết bị trong phòng này")
        elif e.response.status_code == 500:
            SLOG.error(f"Mã one-touch không hợp lệ: {str(e)}")
            raise ValueError(f"Mã one-touch không hợp lệ: {one_touch_code}")
        else:
            SLOG.error(f"Lỗi HTTP khi thực hiện one-touch control: {str(e)}")
            raise
    except Exception as e:
        SLOG.error(f"Lỗi khi thực hiện room one-touch control: {str(e)}")
        raise

@mcp.tool()
async def retrieve_ir_data(token: str, label: str, brandId: int, modelName: str):
    """Retrieve IR data template and models for remote button based on device type and brand
    Args:
        token (str): Token authentication from Oxii API.
        label (str): Type of device (TV, CONDITIONER, FAN).
        brandId (int): ID of the device brand.
        modelName (str): Name of the device model.
    """

    SLOG.info(f"Retrieve IR data: {label}, {brandId}, {modelName}")
    try:
        # on/off device
        url = os.getenv("OXII_ROOT_API_URL") + "/api/app/remote-button/data-ir"
        payload = {
            "label": label,
            "brandId": brandId,
            "modelName": modelName
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {token}",
            'X-Origin': 'smarthiz'
        }
        SLOG.info(f"Retrieve IR data payload: {payload}")
        response = await http_client.get(url, headers=headers, params=payload)
        response.raise_for_status()
        SLOG.info(f"Retrieve IR data response: {response.json()}")
        SLOG.info("-------------------------------------")
        return response.json()
    except Exception as e:
        SLOG.error(f"Lỗi khi lấy dữ liệu IR: {str(e)}")
        raise

@mcp.tool()
async def retrieve_ir_data_v2(token: str, buttonId: int):
    """Retrieve IR data template and models for remote button based on device type and brand
    Args:
        token (str): Token authentication from Oxii API.
        buttonId (int): ID of the remote button.
    """

    room_info = await get_device_list(token)
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
    SLOG.info(f"Retrieve IR data: {buttonId}, {label}, {brandId}, {modelName}")

    try:
        # on/off device
        url = os.getenv("OXII_ROOT_API_URL") + "/api/app/remote-button/data-ir"
        payload = {
            "label": label,
            "brandId": brandId,
            "modelName": modelName
        }
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {token}",
            'X-Origin': 'smarthiz'
        }
        SLOG.info(f"Retrieve IR data payload: {payload}")
        response = await http_client.get(url, headers=headers, params=payload)
        response.raise_for_status()
        SLOG.info(f"Retrieve IR data response: {response.json()}")
        SLOG.info("-------------------------------------")
        return response.json()
    except Exception as e:
        SLOG.error(f"Lỗi khi lấy dữ liệu IR: {str(e)}")
        raise

@mcp.tool()
async def open_ir_send_for_testing_mesh(token: str, serial_numbers: List[str], net_index: int, app_index: int, label: str, brandId: int, modelName: str, label_code: str, command_type: int=212):
    """Send IR command to devices in mesh network for TV, FAN devices, not for CONDITIONER devices
    Args:
        token (str): Token authentication from Oxii API.
        serial_numbers (List[str]): Serial numbers of the devices remoteButton.device.seriNumber.
        net_index (int): Network index for mesh network (house_id).
        app_index (int): Application index for mesh network (thường là 0).
        label (str): Type of device (TV, CONDITIONER, FAN).
        brandId (int): ID of the device brand.
        modelName (str): Name of the device model.
        label_code (str): The code of the label (e.g., "KEY_POWER").
        command_type (int): Command type for IR send (default is 212 for TV/Fan)
    """

    SLOG.info(f"Open IR send for testing mesh: {serial_numbers}, {net_index}, {app_index}, {label}, {brandId}, {modelName}, {label_code}")
    try:
        ir_data_response = await retrieve_ir_data(token, label, brandId, modelName)
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
        SLOG.error(f"Lỗi khi lấy dữ liệu IR: {str(e)}")
        raise
    
    try:
        # Chuẩn bị payload theo đúng định dạng API
        url = os.getenv("OXII_ROOT_API_URL") + "/api/app/device/switch/open-ir-send-for-testing-mesh"
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
            "Authorization": f"Bearer {token}",
            'X-Origin': 'smarthiz'
        }

        SLOG.info(f"Open IR send for testing mesh payload: {payload}")
        response = await http_client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        SLOG.info(f"Open IR send for testing mesh response: {response.json()}")
        SLOG.info("-------------------------------------")
        return "Đã gửi lệnh IR thành công"
    except ValueError as ve:
        SLOG.error(f"Lỗi dữ liệu IR: {str(ve)}")
        raise
    except Exception as e:
        SLOG.error(f"Lỗi khi gửi lệnh IR: {str(e)}")
        raise

@mcp.tool()
async def open_ir_send_for_testing_mesh_v2(token: str, buttonId: int, templateID: int):
    """Send IR command to devices in mesh network for TV, FAN devices, not for CONDITIONER devices
    Args:
        token (str): Token authentication from Oxii API.
        buttonId (int): ID of the remote button.
        templateID (int): The ID of the control template.
    """

    room_info = await get_device_list(token)
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

    SLOG.info(f"Open IR send for testing mesh: {buttonId}, {serial_numbers}, {net_index}, {app_index}, {label}, {brandId}, {modelName}")
    try:
        ir_data_response = await retrieve_ir_data(token, label, brandId, modelName)
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
        SLOG.error(f"Lỗi khi lấy dữ liệu IR: {str(e)}")
        raise
    
    try:
        # Chuẩn bị payload theo đúng định dạng API
        url = os.getenv("OXII_ROOT_API_URL") + "/api/app/device/switch/open-ir-send-for-testing-mesh"
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
            "Authorization": f"Bearer {token}",
            'X-Origin': 'smarthiz'
        }

        SLOG.info(f"Open IR send for testing mesh payload: {payload}")
        response = await http_client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        SLOG.info(f"Open IR send for testing mesh response: {response.json()}")
        SLOG.info("-------------------------------------")
        return "Đã gửi lệnh IR thành công"
    except ValueError as ve:
        SLOG.error(f"Lỗi dữ liệu IR: {str(ve)}")
        raise
    except Exception as e:
        SLOG.error(f"Lỗi khi gửi lệnh IR: {str(e)}")
        raise

@mcp.tool()
async def ac_controls_mesh(token: str, serial_numbers: List[str], net_index: int, app_index: int, vendor: str, power: str, mode: str, temp: str, fan_speed: str, swing_h: str, swing_v: str, quiet: str = None, turbo: str = None, econo: str = None, light: str = None, filter: str = None, clean: str = None, beep: str = None, sleep: int = None, model: int = None, celsius: str = "on"):
    """Send AC IR control commands via BLE Mesh network for CONDITIONER devices
    Args:
        token (str): Token authentication from Oxii API.
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

    SLOG.info(f"AC controls mesh: {serial_numbers}, {vendor}, {power}, {mode}, {temp}, {fan_speed}")
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
        url = os.getenv("OXII_ROOT_API_URL") + "/api/app/device/switch/ac-controls-mesh"
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {token}",
            'X-Origin': 'smarthiz'
        }

        SLOG.info(f"AC controls mesh payload: {payload}")
        response = await http_client.put(url, headers=headers, json=payload)
        response.raise_for_status()
        SLOG.info(f"AC controls mesh response: {response.json()}")
        SLOG.info("-------------------------------------")
        
        return "Đã gửi lệnh điều khiển điều hòa thành công"
    except Exception as e:
        SLOG.error(f"Lỗi khi gửi lệnh điều khiển điều hòa: {str(e)}")
        raise

@mcp.tool()
async def ac_controls_mesh_v2(token: str, buttonId: int, power: str, mode: str='1', temp: str='24', fan_speed: str='0', swing_h: str='0', swing_v: str='0'):
    """Send AC IR control commands via BLE Mesh network for CONDITIONER devices
    Args:
        token (str): Token authentication from Oxii API.
        buttonId (int): ID of the remote button.
        power (str): Power state: '1'/'on' for ON, '0'/'off' for OFF.
        mode (str): AC operating mode ('1'/'auto', '2'/'heat', '3'/'cool', '4'/'dry', '5'/'fan'). Default is '1'.
        temp (str): Target temperature value ("16" to "32"). Default is '25'.
        fan_speed (str): Fan speed ('0'/'auto', '1'/'low', '2'/'medium', '3'/'high', '4'/'turbo'). Default is '1'.
        swing_h (str): Horizontal swing: '1'/'on' for ON, '0'/'off' for OFF. Default is '0'.
        swing_v (str): Vertical swing: '1'/'on' for ON, '0'/'off' for OFF. Default is '0'.
    """

    room_info = await get_device_list(token)
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
    
    SLOG.info(f"AC controls mesh: {buttonId}, {serial_numbers}, {vendor}, {power}, {mode}, {temp}, {fan_speed}")
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
        url = os.getenv("OXII_ROOT_API_URL") + "/api/app/device/switch/ac-controls-mesh"
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json',
            "Authorization": f"Bearer {token}",
            'X-Origin': 'smarthiz'
        }

        SLOG.info(f"AC controls mesh payload: {payload}")
        response = await http_client.put(url, headers=headers, json=payload)
        response.raise_for_status()
        SLOG.info(f"AC controls mesh response: {response.json()}")
        SLOG.info("-------------------------------------")
        
        return "Đã gửi lệnh điều khiển điều hòa thành công"
    except Exception as e:
        SLOG.error(f"Lỗi khi gửi lệnh điều khiển điều hòa: {str(e)}")
        raise


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """
    Health check endpoint for monitoring server status.
    Returns HTTP 200 OK with server status information.
    """
    from starlette.responses import JSONResponse
    
    try:
        # Kiểm tra trạng thái server cơ bản
        server_status = {
            "status": "healthy",
            "service": "MCP Server",
            "version": "1.0.0",
            "timestamp": time.time(),
            "uptime": "running"
        }
        
        SLOG.info("Health check endpoint accessed successfully")
        return JSONResponse(content=server_status, status_code=200)
        
    except Exception as e:
        SLOG.error(f"Health check failed: {str(e)}")
        error_response = {
            "status": "unhealthy",
            "service": "MCP Server",
            "error": str(e),
            "timestamp": time.time()
        }
        return JSONResponse(content=error_response, status_code=503)


if __name__ == "__main__":
    mcp.settings = Settings(port=os.getenv("MCP_SERVER_PORT"), host=os.getenv("MCP_SERVER_HOST"))
    mcp.run(transport=os.getenv("MCP_SERVER_TRANSPORT"))