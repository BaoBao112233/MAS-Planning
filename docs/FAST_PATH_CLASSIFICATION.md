# Fast-Path Intent Classification System

## Tổng quan

Hệ thống phân loại intent và routing tự động cho MAS-Planning system với 4 loại intent chính và execution paths tương ứng.

## Các Intent Classes

### 1. `device_control` - Điều khiển thiết bị
**Routing**: Tool Agent → Manager  
**Thời gian xử lý**: < 1 giây (cho Manager analysis)

**Flow**:
```
User Input → FastPath Classifier 
    → Tool Agent (thực thi command)
    → Manager (phân tích kết quả + trả về user)
```

**Ví dụ**:
- "Bật đèn phòng khách"
- "Turn on the bedroom light"
- "Tắt quạt phòng ngủ"
- "Set temperature to 24 degrees"
- "Tăng độ sáng đèn lên 80%"

**Patterns hỗ trợ**:
- Basic ON/OFF: bật/tắt/turn on/turn off + device
- Temperature control: set temperature/nhiệt độ + số
- Brightness control: set brightness/độ sáng + số
- Fan speed: set speed/tốc độ + level
- Multi-device: bật đèn và quạt

**Output từ Manager**:
- Phân tích kết quả từ Tool Agent
- Thông báo thành công/thất bại
- Thông tin trạng thái thiết bị sau khi thay đổi

---

### 2. `show_device_status` - Hiển thị trạng thái thiết bị
**Routing**: Manager Only (sử dụng tool `get_device_list`)  
**Thời gian xử lý**: < 1 giây

**Flow**:
```
User Input → FastPath Classifier 
    → Manager (gọi get_device_list)
    → Manager (phân tích + format + trả về user)
```

**Không gọi Tool Agent** - Manager tự xử lý bằng `get_device_list` tool

**Ví dụ**:
- "Show me all devices"
- "Hiển thị thiết bị"
- "Trạng thái đèn phòng khách"
- "Devices in the bedroom"
- "Có những thiết bị gì ở phòng ngủ?"

**Patterns hỗ trợ**:
- Status queries: trạng thái/status + device
- List all: show/hiển thị/list + devices
- Room-specific: devices in/ở + room name
- Device state check: device + đang bật/is on?

**Tiêu chí phân tích Manager**:
1. **Phòng nào?**
   - Phân tích từ khóa phòng: phòng khách, phòng ngủ, kitchen, bedroom...
   - Nếu không xác định → hiển thị tất cả phòng

2. **Thông tin hiển thị** (CHỈ thông tin cơ bản):
   - ✅ Tên thiết bị (deviceName)
   - ✅ Trạng thái thiết bị (deviceStatus: on/off)
   - ✅ Tên nút bấm (buttonName)
   - ✅ Trạng thái nút bấm (buttonStatus: on/off)
   - ❌ KHÔNG hiển thị: deviceId, buttonId, roomId, MAC address, IP, technical details

**Format output**:
```
🏠 **Danh sách thiết bị**

📍 **Phòng khách** (3 thiết bị)
  • **Đèn trần** - 🟢 Bật
     ◦ Nút 1: 🟢 Bật
     ◦ Nút 2: ⚪ Tắt
  • **Quạt trần** - ⚪ Tắt
  • **Máy lạnh** - 🟢 Bật

📊 **Tổng cộng**: 3 thiết bị
```

---

### 3. `planning` - Tạo kế hoạch tự động hóa
**Routing**: Manager → Plan Agent → (User chọn) → Tool Agent → Manager  
**Thời gian xử lý Manager**: < 1 giây (ở các bước phân tích)

**Flow**:
```
User Input → FastPath Classifier
    → Manager (phân tích yêu cầu - <1s)
    → Plan Agent (tạo 2 plans dựa trên devices)
    → User (chọn plan 1 hoặc 2)
    → Tool Agent (thực thi plan)
    → Manager (phân tích kết quả - <1s)
    → User (kết quả cuối cùng)
```

**Ví dụ**:
- "Tạo kế hoạch tự động hóa cho phòng ngủ"
- "Create automation plan"
- "Setup routine for bedroom"
- "Lên lịch bật đèn lúc 6 giờ sáng"
- "Khi tôi về nhà thì bật đèn"

**Plan selection**:
- "Plan 1" / "Chọn kế hoạch 1"
- "Option 2" / "Lựa chọn 2"

**Patterns hỗ trợ**:
- Create plan: tạo/create + kế hoạch/plan/automation
- Schedule: lên lịch/schedule + task + time
- Conditional: khi/when + condition + thì/then + action
- Plan selection: plan/option + số

**Plan Agent workflow**:
1. Gọi `get_device_list` để lấy thông tin thiết bị hiện có
2. Phân tích yêu cầu người dùng
3. Tạo 2 plans ưu tiên khác nhau (Optimized vs Conservative)
4. Trả về cho user chọn
5. User chọn → Tool Agent thực thi
6. Manager phân tích và trả kết quả (<1s)

---

### 4. `unknown` - Query không xác định
**Routing**: Manager Only  
**Thời gian xử lý**: < 1 giấy

**Flow**:
```
User Input → FastPath Classifier (no pattern match)
    → Manager (trả lời trực tiếp - <1s)
```

**Không delegate** cho bất kỳ Agent nào khác

**Ví dụ**:
- "Hello"
- "What is smart home?"
- "How are you?"
- Bất kỳ query nào không match patterns

**Manager response**:
- Trả lời chung về system
- Hướng dẫn sử dụng
- Câu hỏi thông tin cơ bản

---

## API Usage

### Basic Classification

```python
from template.agent.manager.fast_path import get_fast_path_classifier, IntentClass, ExecutionPath

# Get classifier instance
classifier = get_fast_path_classifier(verbose=True)

# Classify query
result = classifier.classify("Bật đèn phòng khách", token="user_token")

if result:
    print(f"Intent: {result.intent.value}")
    print(f"Execution Path: {result.execution_path.value}")
    print(f"Confidence: {result.confidence}")
    print(f"Params: {result.extracted_params}")
    print(f"Reasoning: {result.reasoning}")
```

### Classification Result

```python
@dataclass
class ClassificationResult:
    intent: IntentClass              # DEVICE_CONTROL, SHOW_DEVICE_STATUS, PLANNING, UNKNOWN
    confidence: float                # 0.0 - 1.0
    execution_path: ExecutionPath    # TOOL_THEN_MANAGER, MANAGER_ONLY, FULL_PLANNING
    method: str                      # 'pattern' or 'fallback'
    extracted_params: Dict[str, Any] # Extracted parameters
    reasoning: str                   # Why this classification
```

### Routing Logic in Manager

```python
# In Manager Agent
result = classifier.classify(user_input, token)

if result.execution_path == ExecutionPath.TOOL_THEN_MANAGER:
    # device_control: Tool → Manager
    tool_result = tool_agent.invoke(user_input, token)
    final_answer = manager_analyze_result(tool_result)  # <1s
    
elif result.execution_path == ExecutionPath.MANAGER_ONLY:
    if result.intent == IntentClass.SHOW_DEVICE_STATUS:
        # show_device_status: Manager uses get_device_list
        device_list = call_get_device_list(token)
        final_answer = classifier.format_device_status_response(
            device_list, 
            result.extracted_params
        )  # <1s
    else:
        # unknown: Manager direct response
        final_answer = generate_direct_response(user_input)  # <1s
    
elif result.execution_path == ExecutionPath.FULL_PLANNING:
    # planning: Full workflow
    manager_analysis = manager_analyze(user_input)  # <1s
    plan_options = plan_agent.create_plans(manager_analysis, token)
    
    # Wait for user selection
    selected_plan = get_user_selection()
    
    # Execute selected plan
    execution_result = tool_agent.execute_plan(selected_plan, token)
    final_answer = manager_analyze_result(execution_result)  # <1s
```

## Performance Targets

| Intent Class | Execution Path | Manager Processing Time | Total Flow Time |
|-------------|----------------|------------------------|-----------------|
| device_control | Tool → Manager | < 1s | ~2-3s (Tool execution) |
| show_device_status | Manager only | < 1s | < 1s (get_device_list) |
| planning | Manager → Plan → Tool → Manager | < 1s per step | Varies (user interaction) |
| unknown | Manager only | < 1s | < 1s |

## Pattern Examples

### Device Control Patterns
```python
# Vietnamese
"Bật đèn phòng khách"           → device_control, turn_on
"Tắt quạt phòng ngủ"            → device_control, turn_off
"Đặt nhiệt độ 24 độ"            → device_control, set_temperature
"Tăng độ sáng lên 80%"          → device_control, set_brightness

# English
"Turn on the living room light" → device_control, turn_on
"Set AC to 22 degrees"          → device_control, set_temperature
"Turn off bedroom fan"          → device_control, turn_off
```

### Show Device Status Patterns
```python
# Vietnamese
"Hiển thị thiết bị"                      → show_device_status, list_all
"Trạng thái đèn phòng khách"             → show_device_status, get_status
"Có những thiết bị gì ở phòng ngủ?"     → show_device_status, devices_in_room
"Đèn có đang bật không?"                 → show_device_status, check_state

# English
"Show me all devices"                    → show_device_status, list_all
"List devices in bedroom"                → show_device_status, devices_in_room
"Status of living room light"            → show_device_status, get_status
```

### Planning Patterns
```python
# Vietnamese
"Tạo kế hoạch tự động hóa cho phòng ngủ" → planning, create_plan
"Lên lịch bật đèn lúc 6 giờ sáng"       → planning, schedule
"Khi tôi về nhà thì bật đèn"            → planning, conditional

# English
"Create automation plan"                 → planning, create_plan
"Schedule turn on light at 6am"          → planning, schedule
"When I arrive home then turn on light"  → planning, conditional

# Plan Selection
"Plan 1"                                 → planning, select_plan
"Chọn kế hoạch 2"                        → planning, select_plan
```

## Adding New Patterns

### 1. Define Pattern in `_build_patterns()`

```python
patterns.extend([
    {
        'regex': re.compile(r'^your_regex_pattern$', re.IGNORECASE),
        'intent': IntentClass.DEVICE_CONTROL,  # Choose appropriate intent
        'action': 'your_action_name',
        'confidence': 0.92,
        'description': 'Human readable description'
    },
])
```

### 2. Update `_extract_params()` if needed

```python
elif action == 'your_action_name':
    if len(groups) >= 1:
        params['custom_param'] = groups[0].strip()
```

### 3. Test the pattern

```python
result = classifier.classify("your test query")
assert result.intent == IntentClass.DEVICE_CONTROL
assert result.extracted_params['custom_param'] == 'expected_value'
```

## Integration with Manager Agent

File `template/agent/manager/__init__.py` đã được update để sử dụng FastPathClassifier:

```python
# In analyze_query()
if self.use_fast_path:
    fast_result = self.fast_path.classify(user_input, token)
    if fast_result and fast_result.confidence >= self.fast_path_threshold:
        # Use fast-path classification
        return build_fast_path_state(fast_result)

# Fallback to LLM analysis
```

## Notes

1. **Sub-second requirement**: Tất cả Manager processing steps phải < 1 giây
2. **No technical details**: show_device_status KHÔNG hiển thị deviceId, buttonId, IPs, MACs
3. **Manager only paths**: SHOW_DEVICE_STATUS và UNKNOWN không gọi Tool/Plan Agents
4. **Pattern priority**: Patterns được match theo thứ tự, pattern đầu tiên match sẽ được dùng
5. **Confidence threshold**: Default 0.85, có thể adjust theo yêu cầu

## Future Enhancements

1. **ML-based classification**: Fallback khi không match patterns
2. **Caching**: Cache classifications cho repeated queries
3. **Learning**: Học từ user feedback để improve patterns
4. **Multi-language**: Support thêm ngôn ngữ khác
