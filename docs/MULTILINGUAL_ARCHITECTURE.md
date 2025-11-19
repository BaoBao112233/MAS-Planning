# Multilingual Architecture

## Overview

Hệ thống MAS-Planning sử dụng kiến trúc **centralized translation** với Manager Agent là layer chịu trách nhiệm đảm bảo tất cả output (bao gồm cả error messages) đúng với ngôn ngữ người dùng chọn từ client.

## Architecture Flow

```
Client (language_code: vi-VN/en-US)
    ↓
FastAPI Router (receives language_code)
    ↓
Manager Agent (stores self.language_code)
    ↓
├─→ Plan Agent (receives language_code)
│   ├─ LLM with language instruction
│   └─ format_plan_response(language_code)
│
├─→ Tool Agent (receives language_code)
│   ├─ API Functions (NO language_code needed)
│   │   └─ Return data in default language (Vietnamese)
│   └─ format_tool_response(language_code)
│       └─ TRANSLATION LAYER (translates if needed)
│
└─→ Direct Response
    └─ format_final_response(language_code)
```

## Key Design Principles

### 1. **Separation of Concerns**

- **API Layer**: Chỉ xử lý business logic, không quan tâm ngôn ngữ
- **Manager Layer**: Xử lý presentation logic, đảm bảo ngôn ngữ đúng
- **Benefit**: API functions đơn giản, không cần pass `language_code` khắp nơi

### 2. **Centralized Translation**

Tất cả translation logic tập trung tại `template/agent/manager/utils.py`:

- `format_final_response()`: Route chính cho mọi output
- `format_plan_response()`: Format Plan Agent với multilingual templates
- `format_tool_response()`: Format Tool Agent + **Translation Layer**

### 3. **Translation Layer in Manager**

**Location**: `template/agent/manager/utils.py` - `format_tool_response()`

**Function**: Detect và translate Vietnamese messages từ API sang English nếu user chọn English

**Example**:
```python
# API returns: "Không tìm thấy thông tin nhà"
# User selected: en-US
# Manager translates to: "Home information not found"
```

## Translation Mappings

### Device Status

| Vietnamese | English |
|------------|---------|
| Không thể kết nối | Cannot connect |
| Đang kết nối | Connected |
| bật | on |
| tắt | off |

### Error Messages

| Vietnamese | English |
|------------|---------|
| Không tìm thấy thông tin nhà | Home information not found |
| Không tìm thấy thiết bị | Device not found |
| Không tìm thấy phòng | Room not found |
| Lỗi khi lấy danh sách thiết bị | Error retrieving device list |
| Lỗi khi gửi lệnh | Error sending command |
| Lỗi kết nối | Connection error |

### Success Messages

| Vietnamese | English |
|------------|---------|
| Yêu cầu đã được xử lý thành công | Request processed successfully |
| Đã xử lý xong | Processed |
| Thành công | Success |
| Hoàn thành | Completed |

### Action Messages

| Vietnamese | English |
|------------|---------|
| Tất cả thiết bị đã được | All devices have been |
| thành công | successfully |
| Đang bật | Turning on |
| Đang tắt | Turning off |

## Code Examples

### 1. API Function (No Language Parameter)

```python
# template/api_things/info_devices.py
def get_device_list(is_format_toon: bool = True):
    """
    Get device list from Oxii API.
    Returns data in default language (Vietnamese).
    Manager will translate if needed.
    """
    try:
        # ... API logic ...
        if not home:
            return "Không tìm thấy thông tin nhà"  # Vietnamese
        
        # ... return device list ...
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách thiết bị: {str(e)}")
        raise
```

### 2. Manager Translation Layer

```python
# template/agent/manager/utils.py
def format_tool_response(agent_result, query, language_code="en-US"):
    """Format Tool Agent response with translation"""
    output = agent_result.get('output', '')
    is_vietnamese = language_code.startswith('vi')
    
    # ... cleaning logic ...
    
    # TRANSLATION LAYER: If user wants English, translate Vietnamese
    if not is_vietnamese and cleaned_output:
        translations = {
            "Không tìm thấy thông tin nhà": "Home information not found",
            "Lỗi khi lấy danh sách thiết bị": "Error retrieving device list",
            # ... more translations ...
        }
        
        for vi_text, en_text in translations.items():
            cleaned_output = cleaned_output.replace(vi_text, en_text)
    
    return cleaned_output
```

### 3. Plan Agent with LLM Instructions

```python
# template/agent/plan/__init__.py
def _create_priority_plans(self, user_input, device_list_data):
    """Create plans with language instruction for LLM"""
    
    # Language instruction for LLM
    is_vietnamese = self.language_code.startswith('vi')
    if is_vietnamese:
        language_instruction = (
            "BẮT BUỘC: Trả lời HOÀN TOÀN bằng Tiếng Việt. "
            "Tất cả plan, task, giải thích phải là Tiếng Việt."
        )
    else:
        language_instruction = (
            "MANDATORY: Respond ENTIRELY in English. "
            "All plans, tasks, explanations must be in English."
        )
    
    system_message = f"{language_instruction}\n\nYou are an expert..."
    # ... LLM call with system message ...
```

## Benefits of This Architecture

### ✅ Pros

1. **Simplicity**: API functions không cần quan tâm language
2. **Maintainability**: Translation logic tập trung một chỗ
3. **Flexibility**: Dễ dàng add thêm ngôn ngữ mới
4. **Backward Compatibility**: Existing API không cần thay đổi
5. **Clear Separation**: Business logic vs Presentation logic

### ⚠️ Considerations

1. **Translation Dictionary**: Cần maintain danh sách translations
2. **Partial Matches**: String replacement có thể miss một số cases
3. **Context-Dependent**: Một số từ có thể có nhiều nghĩa

## Testing

### Test Case 1: Vietnamese User

```
Input: 
- language_code: "vi-VN"
- API returns: "Không tìm thấy thông tin nhà"

Expected Output:
- "Không tìm thấy thông tin nhà" (unchanged)
```

### Test Case 2: English User

```
Input:
- language_code: "en-US"
- API returns: "Không tìm thấy thông tin nhà"

Expected Output:
- "Home information not found" (translated)
```

### Test Case 3: Mixed Content

```
Input:
- language_code: "en-US"
- API returns: "Device Đèn trần is bật in Living room"

Expected Output:
- "Device Đèn trần is on in Living room" (partially translated)
```

## Adding New Translations

To add new translations, update the `translations` dictionary in `format_tool_response()`:

```python
translations = {
    # ... existing translations ...
    
    # Add your new translations here
    "Vietnamese text": "English text",
    "Thêm thiết bị mới": "Add new device",
}
```

## Future Enhancements

### 1. External Translation Service

Replace dictionary-based translation with Google Translate API or similar:

```python
def translate_text(text: str, target_language: str) -> str:
    """Use external translation service"""
    if target_language == "en":
        # Call Google Translate API
        return google_translate(text, source="vi", target="en")
    return text
```

### 2. LLM-Based Translation

Use LLM to translate complex messages while preserving technical terms:

```python
def llm_translate(text: str, target_language: str) -> str:
    """Use LLM for context-aware translation"""
    prompt = f"Translate to {target_language}, keep device names: {text}"
    return llm.invoke(prompt)
```

### 3. Translation Cache

Cache translated messages để tránh translate lại nhiều lần:

```python
translation_cache = {}

def get_translation(text: str, target_lang: str) -> str:
    key = f"{text}:{target_lang}"
    if key not in translation_cache:
        translation_cache[key] = translate(text, target_lang)
    return translation_cache[key]
```

## Error Handling Translation

Manager cũng translate các HTTP error codes thành user-friendly messages:

```python
# 500 Internal Server Error
if '500' in output_lower:
    if is_vietnamese:
        return "❌ Không thể kết nối với thiết bị. Vui lòng thử lại."
    else:
        return "❌ Unable to connect to device. Please try again."

# 401 Unauthorized
if '401' in output_lower:
    if is_vietnamese:
        return "🔐 Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."
    else:
        return "🔐 Session expired. Please login again."
```

## Summary

**Q: Tại sao không thêm `language_code` vào tất cả API functions?**

**A: Vì:**
1. API functions chỉ nên xử lý business logic, không phải presentation
2. Centralized translation dễ maintain hơn scattered translations
3. Manager Agent là nơi tốt nhất để handle user-facing concerns
4. Giữ cho API layer clean và reusable

**Q: Điều gì xảy ra nếu API return data chứa Vietnamese text?**

**A: Manager's Translation Layer sẽ:**
1. Detect language_code từ client
2. Nếu user chọn English, apply translations
3. Replace Vietnamese text với English equivalents
4. Return cleaned, translated output to user

**Q: Làm sao add thêm ngôn ngữ mới (e.g., French, Spanish)?**

**A:**
1. Extend translations dictionary với mappings mới
2. Update `is_vietnamese` logic thành language detection
3. Add language instructions cho LLM
4. Test với new language_code (e.g., "fr-FR", "es-ES")

---

**Last Updated**: 2025-01-19  
**Version**: 1.0  
**Status**: ✅ Implemented & Tested
