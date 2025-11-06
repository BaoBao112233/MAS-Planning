# Fast-Path Classification System - Quick Start

## 🚀 Quick Start

### 1. Run Demo (Recommended First Step)

```bash
cd /home/baobao/Projects/MAS-Planning
python demo_fast_path.py
```

**Output**: Interactive demo showing all 4 intent classes and execution paths

---

### 2. Run Tests

```bash
python test_folders/test_fast_path_classification.py
```

**Output**: Comprehensive test suite với 100+ test cases

---

### 3. Basic Usage in Code

```python
from template.agent.manager.fast_path import get_fast_path_classifier

# Get classifier instance (singleton)
classifier = get_fast_path_classifier(verbose=True)

# Classify user input
result = classifier.classify("Bật đèn phòng khách", token="user_token")

# Check result
print(f"Intent: {result.intent.value}")
print(f"Execution Path: {result.execution_path.value}")
print(f"Confidence: {result.confidence}")
print(f"Params: {result.extracted_params}")
```

---

## 📋 4 Intent Classes Overview

| Intent | Execution Path | Manager Time | Example |
|--------|---------------|--------------|---------|
| **device_control** | Tool → Manager | < 1s | "Bật đèn phòng khách" |
| **show_device_status** | Manager only | < 1s | "Show all devices" |
| **planning** | Manager → Plan → Tool → Manager | < 1s/step | "Tạo automation plan" |
| **unknown** | Manager only | < 1s | "Hello" |

---

## 🔄 Execution Paths Detail

### 1️⃣ DEVICE_CONTROL → TOOL_THEN_MANAGER

```
User Input → Tool Agent → Manager (analyze) → User
                            ^^^^^^^^
                            < 1 second
```

**Manager tasks**:
- Analyze Tool Agent result
- Format user-friendly response
- Handle success/error cases

**Examples**:
- "Bật đèn phòng khách"
- "Turn on bedroom light"
- "Set AC to 24 degrees"

---

### 2️⃣ SHOW_DEVICE_STATUS → MANAGER_ONLY

```
User Input → Manager (get_device_list + format) → User
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                       < 1 second
```

**Manager tasks**:
- Call `get_device_list` tool directly
- Analyze which room(s) user wants
- Format device info (NO technical details)
- Return formatted response

**What to show** ✅:
- Device name
- Device status (on/off)
- Button name
- Button status

**What NOT to show** ❌:
- deviceId, buttonId, roomId
- MAC address, IP address
- Any technical/internal IDs

**Examples**:
- "Show me all devices"
- "Hiển thị thiết bị phòng khách"
- "What devices in bedroom?"

---

### 3️⃣ PLANNING → FULL_PLANNING

```
User Input → Manager (analyze) → Plan Agent → User selects → Tool Agent → Manager (analyze) → User
              ^^^^^^^^^                                                     ^^^^^^^^^
              < 1 second                                                    < 1 second
```

**Manager tasks** (2 steps):
1. **Before Plan Agent**: Analyze user requirements (< 1s)
2. **After Tool Agent**: Analyze execution results (< 1s)

**Examples**:
- "Tạo kế hoạch automation"
- "Create plan for bedroom"
- "Plan 1" (selecting plan)

---

### 4️⃣ UNKNOWN → MANAGER_ONLY

```
User Input → Manager (direct response) → User
              ^^^^^^^^^^^^^^^^^^^^
                   < 1 second
```

**Manager tasks**:
- Generate helpful direct response
- Provide system info/guidance
- No delegation to other agents

**Examples**:
- "Hello"
- "What is smart home?"
- Any unmatched query

---

## 🎯 Performance Requirements

| Operation | Target | Actual |
|-----------|--------|--------|
| Classification | < 100ms | ~5-10ms |
| Manager analysis (device_control) | < 1s | TBD |
| Manager formatting (show_device_status) | < 1s | TBD |
| Manager analysis (planning step) | < 1s | TBD |
| Manager response (unknown) | < 1s | TBD |

---

## 📁 File Structure

```
/home/baobao/Projects/MAS-Planning/
│
├── template/agent/manager/
│   ├── __init__.py              # Manager Agent (integration point)
│   └── fast_path.py             # ✅ Fast-Path Classifier
│
├── docs/
│   ├── FAST_PATH_CLASSIFICATION.md  # Full documentation
│   └── ...
│
├── test_folders/
│   └── test_fast_path_classification.py  # Test suite
│
├── demo_fast_path.py            # ✅ Quick demo script
├── FAST_PATH_UPDATE_SUMMARY.md  # ✅ Update summary
└── FAST_PATH_QUICKSTART.md      # ✅ This file
```

---

## 🔧 Integration with Manager Agent

### Step 1: Classification

```python
# In Manager Agent's analyze_query()
result = self.fast_path.classify(user_input, token)

if result:
    # Use fast-path classification
    intent = result.intent
    execution_path = result.execution_path
    params = result.extracted_params
```

### Step 2: Routing Based on Execution Path

```python
if execution_path == ExecutionPath.TOOL_THEN_MANAGER:
    # 1. Call Tool Agent
    tool_result = self.tool_agent.invoke(user_input, token)
    
    # 2. Manager analyzes result (< 1s)
    final_answer = self._analyze_tool_result(tool_result)
    return final_answer

elif execution_path == ExecutionPath.MANAGER_ONLY:
    if intent == IntentClass.SHOW_DEVICE_STATUS:
        # Manager uses get_device_list
        device_list = self._call_get_device_list(token)
        
        # Format response (< 1s)
        final_answer = self.fast_path.format_device_status_response(
            device_list,
            params
        )
        return final_answer
    
    else:  # UNKNOWN
        # Direct response (< 1s)
        final_answer = self._generate_direct_response(user_input)
        return final_answer

elif execution_path == ExecutionPath.FULL_PLANNING:
    # 1. Manager analyzes (< 1s)
    analysis = self._analyze_planning_request(user_input)
    
    # 2. Plan Agent creates plans
    plans = self.plan_agent.invoke(user_input, token, analysis)
    
    # 3. Wait for user selection
    # ... (handled in separate interaction)
    
    # 4. Tool Agent executes selected plan
    # ... (after user selects)
    
    # 5. Manager analyzes result (< 1s)
    # ... (final step)
```

---

## 🧪 Testing Your Integration

### Test 1: Device Control

```python
# Input: "Bật đèn phòng khách"
# Expected:
# - Intent: device_control
# - Path: TOOL_THEN_MANAGER
# - Flow: Tool executes → Manager analyzes (< 1s)
```

### Test 2: Show Devices

```python
# Input: "Show all devices"
# Expected:
# - Intent: show_device_status
# - Path: MANAGER_ONLY
# - Flow: Manager uses get_device_list + formats (< 1s)
```

### Test 3: Planning

```python
# Input: "Tạo automation plan"
# Expected:
# - Intent: planning
# - Path: FULL_PLANNING
# - Flow: Manager analyzes → Plan creates → User selects → Tool executes → Manager analyzes
```

### Test 4: Unknown

```python
# Input: "Hello"
# Expected:
# - Intent: unknown
# - Path: MANAGER_ONLY
# - Flow: Manager direct response (< 1s)
```

---

## 📊 Pattern Coverage

### Supported Patterns

| Category | Vietnamese | English | Total |
|----------|-----------|---------|-------|
| Device Control | ✅ | ✅ | 9+ |
| Show Device Status | ✅ | ✅ | 6+ |
| Planning | ✅ | ✅ | 5+ |
| Unknown | Fallback | Fallback | - |

### Example Patterns

**Device Control**:
- "Bật đèn phòng khách"
- "Turn on bedroom light"
- "Set AC to 24 degrees"
- "Tăng độ sáng lên 80%"

**Show Device Status**:
- "Show all devices"
- "Hiển thị thiết bị"
- "Status of living room light"
- "Devices in bedroom"

**Planning**:
- "Tạo automation plan"
- "Create plan for bedroom"
- "Plan 1"
- "Schedule turn on light at 6am"

---

## 🐛 Troubleshooting

### Issue: Classification returns None

**Cause**: No pattern matched  
**Solution**: Query is classified as `unknown` with confidence 0.5

### Issue: Wrong intent detected

**Cause**: Pattern priority mismatch  
**Solution**: Check pattern order in `_build_patterns()`, first match wins

### Issue: Parameters not extracted

**Cause**: Regex groups don't match query structure  
**Solution**: Check `_extract_params()` logic for that action type

### Issue: Manager processing > 1s

**Cause**: Heavy LLM calls or slow tool execution  
**Solution**: 
- Use lightweight analysis prompts
- Cache common responses
- Optimize tool calls

---

## 📚 Full Documentation

For complete details, see:
- **Full docs**: `docs/FAST_PATH_CLASSIFICATION.md`
- **Update summary**: `FAST_PATH_UPDATE_SUMMARY.md`
- **Source code**: `template/agent/manager/fast_path.py`

---

## 🎯 Next Steps

1. ✅ Run demo: `python demo_fast_path.py`
2. ✅ Run tests: `python test_folders/test_fast_path_classification.py`
3. ⏳ Integrate with Manager Agent routing
4. ⏳ Implement Manager's `get_device_list` call
5. ⏳ Add Manager result analysis for device_control
6. ⏳ Test end-to-end flows

---

**Version**: 1.0.0  
**Last Updated**: 2025-11-05  
**Status**: ✅ Ready for Integration
