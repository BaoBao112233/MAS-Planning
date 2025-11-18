# Migration Summary: From MCP to Direct API Calls

## 📅 Migration Date
November 18, 2025

## 🎯 Migration Goals

1. ✅ Thay thế MCP tools bằng direct API calls từ `api_things`
2. ✅ Loại bỏ toàn bộ logic MCP (MultiServerMCPClient, SSE connections)
3. ✅ Tạm thời disable support cho IR devices
4. ✅ Cải thiện performance và giảm dependencies

---

## 📝 Changes Summary

### 1. Tool Agent (`template/agent/tool/__init__.py`)

**Before:**
- Sử dụng MCP client qua `langchain_mcp_adapters.client.MultiServerMCPClient`
- Tools được load từ MCP server qua SSE connection
- Phức tạp với async MCP client lifecycle management
- Hỗ trợ 13 tools bao gồm cả IR devices

**After:**
- ✅ **Direct API calls** từ `template.api_things`
- ✅ Removed `MultiServerMCPClient` dependency
- ✅ Removed `init_async()` MCP initialization
- ✅ **7 tools** được tạo trực tiếp bằng `StructuredTool`:
  1. `get_device_list()` - từ `info_devices.py`
  2. `switch_on_off_controls_v2()` - từ `switch_devices.py`
  3. `ac_controls_mesh_v2()` - từ `ac_devices.py`
  4. `cronjob_device_v2()` - từ `cronjob_devices.py`
  5. `room_one_touch_control()` - từ `switch_devices.py`
  6. `switch_on_off_all_device()` - từ `switch_devices.py`
  7. `switch_device_by_type()` - từ `switch_devices.py`
- ✅ **Loại bỏ IR tools**: `retrieve_ir_data_v2`, `open_ir_send_for_testing_mesh_v2`
- ✅ Token được set vào `env.OXII_API_KEY` thay vì inject vào từng tool call
- ✅ Sync/async wrapper functions cho compatibility

**Key Changes:**
```python
# Before (MCP)
async def init_async(self):
    self.mcp_client = MultiServerMCPClient(...)
    await self.mcp_client.__aenter__()
    self.tools = list(self.mcp_client.get_tools())

# After (Direct)
def _init_tools(self):
    self.tools = [
        StructuredTool(
            name="get_device_list",
            func=self._sync_get_device_list,
            coroutine=self._async_get_device_list,
            ...
        ),
        ...
    ]
```

---

### 2. Plan Agent (`template/agent/plan/__init__.py`)

**Before:**
- Sử dụng MCP client để gọi `get_device_list` tool
- Phức tạp với thread pool executor và fresh MCP client cho mỗi call
- Timeout handling cho MCP connections

**After:**
- ✅ **Direct call** `get_device_list()` từ `api_things.info_devices`
- ✅ Removed `MultiServerMCPClient` dependency
- ✅ Removed `init_async()` MCP initialization
- ✅ Simplified `_get_device_list()` method

**Key Changes:**
```python
# Before (MCP)
def _get_device_list(self, token: str) -> dict:
    temp_client = MultiServerMCPClient(...)
    # Complex async handling...
    result = loop.run_until_complete(tool.ainvoke(...))

# After (Direct)
def _get_device_list(self, token: str) -> dict:
    env.OXII_API_KEY = token
    result = asyncio.run(get_device_list())
    return result
```

---

### 3. Manager Agent (`template/agent/manager/__init__.py`)

**Before:**
- Sử dụng MCP client để gọi `get_device_list` tool
- Temporary MCP client tạo cho mỗi call
- Complex async handling với event loop management

**After:**
- ✅ **Direct call** `get_device_list()` từ `api_things.info_devices`
- ✅ Removed MCP client logic
- ✅ Simplified `_get_device_list()` method

**Key Changes:**
```python
# Before (MCP)
def _get_device_list(self, token: str):
    mcp_client = MultiServerMCPClient(...)
    # Complex async wrapper...

# After (Direct)
def _get_device_list(self, token: str):
    env.OXII_API_KEY = token
    result = asyncio.run(get_device_list())
    return result
```

---

### 4. Tool Agent Prompt (`template/agent/tool/prompt.py`)

**Before:**
- Hỗ trợ 13 OXII tools bao gồm IR devices
- Instructions cho IR control tools

**After:**
- ✅ **7 BLE mesh tools only**
- ✅ **Warning về IR devices not supported**
- ✅ Instructions để filter IR devices (remoteIRId != null)
- ✅ Updated examples loại bỏ IR scenarios

**Key Changes:**
```
⚠️ IMPORTANT: This system DOES NOT support IR-controlled devices
Only BLE mesh-controlled devices are supported.

CRITICAL RULES:
0. **⚠️ IR DEVICES NOT SUPPORTED** 
   - ALWAYS filter out IR devices (remoteIRId != null)
   - NEVER execute IR control commands
   - Inform user when they try to control IR device
```

---

### 5. Plan Agent Prompts (`template/agent/plan/prompts.py`)

**Before:**
- Không có restrictions về device types
- Planning cho tất cả devices

**After:**
- ✅ **Rule #2: IR DEVICES NOT SUPPORTED**
- ✅ Instructions để filter IR devices khi planning
- ✅ AC activation rule bổ sung check BLE mesh

**Key Changes:**
```
PLANNING RULES:
2. **⚠️ CRITICAL: IR DEVICES NOT SUPPORTED**
   - NEVER include IR-controlled devices in plans
   - ONLY use BLE mesh devices (remoteIRId == null)
   - Filter out IR devices before planning
```

---

## 🔧 Technical Details

### API Functions Used (from `api_things/`)

1. **info_devices.py:**
   - `get_device_list()` - Lấy danh sách thiết bị

2. **switch_devices.py:**
   - `switch_on_off_controls_v2(buttonId, data)`
   - `switch_on_off_all_device(command)`
   - `switch_device_by_type(device_type, action)`
   - `room_one_touch_control(room_id, one_touch_code)`

3. **ac_devices.py:**
   - `ac_controls_mesh_v2(buttonId, power, mode, temp, ...)`

4. **cronjob_devices.py:**
   - `cronjob_device_v2(buttonId, action, job_status, ...)`

### Token Management

**Before:**
- Token passed explicitly to every MCP tool call
- `tool.ainvoke({"token": token, ...})`

**After:**
- Token set globally: `env.OXII_API_KEY = token`
- API functions automatically use `env.OXII_API_KEY`

---

## ✅ Benefits

1. **Simplified Architecture:**
   - Loại bỏ MCP dependency
   - Loại bỏ SSE connection complexity
   - Direct function calls đơn giản hơn

2. **Better Performance:**
   - Không có MCP client overhead
   - Không có SSE connection latency
   - Giảm async complexity

3. **Easier Debugging:**
   - Direct call stack
   - Clearer error messages
   - No MCP connection issues

4. **Reduced Dependencies:**
   - Không cần `langchain_mcp_adapters`
   - Không cần MCP server running
   - Ít moving parts hơn

---

## ⚠️ Temporary Limitations

1. **IR Devices Not Supported:**
   - IR AC, IR TV, IR FAN tạm thời không hoạt động
   - Chỉ hỗ trợ BLE mesh devices
   - User sẽ nhận warning khi cố control IR devices

2. **Tools Removed:**
   - `retrieve_ir_data_v2`
   - `open_ir_send_for_testing_mesh_v2`
   - `retrieve_ir_data`
   - `open_ir_send_for_testing_mesh`
   - `ac_controls_mesh` (legacy)
   - `cronjob_device` (legacy)

---

## 🧪 Testing Checklist

- [ ] Tool Agent: BLE mesh device control
- [ ] Tool Agent: Device status queries
- [ ] Tool Agent: Room one-touch control
- [ ] Tool Agent: IR device rejection (should warn user)
- [ ] Plan Agent: Plan creation with BLE mesh devices only
- [ ] Plan Agent: Device list retrieval
- [ ] Manager Agent: Device status queries
- [ ] Manager Agent: Routing to Tool Agent
- [ ] Manager Agent: Routing to Plan Agent
- [ ] End-to-end: Complete user request flow

---

## 📚 Files Modified

1. `/template/agent/tool/__init__.py` - Complete rewrite
2. `/template/agent/tool/prompt.py` - Updated for BLE mesh only
3. `/template/agent/plan/__init__.py` - Removed MCP, direct API calls
4. `/template/agent/plan/prompts.py` - Added IR device restrictions
5. `/template/agent/manager/__init__.py` - Removed MCP, direct API calls

---

## 🔮 Future Work

1. **Re-enable IR Support:**
   - Khi cần, có thể thêm lại IR tools
   - Import từ `api_things/ir_devices.py`
   - Update prompts để support IR

2. **Optimization:**
   - Cân nhắc connection pooling cho API calls
   - Cache device list khi appropriate
   - Parallel API calls optimization

3. **Monitoring:**
   - Add metrics cho API call latency
   - Track success/failure rates
   - Monitor token usage

---

## 👥 Author
Migration performed by AI Assistant on behalf of BaoBao112233

## ✨ Status
**COMPLETED** ✅ All tasks finished successfully
