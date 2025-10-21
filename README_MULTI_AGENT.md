# MAS-Planning: Multi-Agent System for Planning and Analysis

Hệ thống Multi-Agent với 2 agents chính: Plan Agent và Meta Agent.

## Cấu trúc hệ thống

### 1. Plan Agent (`PlanAgent`)
- **Chức năng**: Chuyên về lập kế hoạch, tổ chức công việc, chia nhỏ mục tiêu
- **Khi nào được kích hoạt**: Khi người dùng nhập các từ khóa liên quan đến planning như:
  - Tiếng Anh: plan, planning, schedule, organize, task, todo, steps
  - Tiếng Việt: kế hoạch, lập kế hoạch, sắp xếp, tổ chức, công việc, bước

### 2. Meta Agent (`MetaAgent`)
- **Chức năng**: Chuyên về phân tích, suy luận, giải thích các khái niệm
- **Khi nào được kích hoạt**: Khi người dùng nhập các từ khóa liên quan đến analysis như:
  - Tiếng Anh: analyze, think, reason, understand, explain, meta, why, how
  - Tiếng Việt: phân tích, suy nghĩ, lý giải, hiểu, giải thích, tại sao, như thế nào

### 3. Multi-Agent System (`MultiAgentSystem`)
- **Chức năng**: Điều phối giữa các agents, tự động route request đến agent phù hợp
- **Default**: Nếu không khớp với keywords nào, sẽ chọn Meta Agent

## Cài đặt và chạy

### 1. Cài đặt dependencies

```bash
pip install -r requirements-dev.txt
```

### 2. Cấu hình môi trường

Tạo file `.env` với nội dung:

```env
# Application settings
API_VERSION=v1.0.0
APP_NAME=MAS Planning System
APP_DESC=Multi-Agent System for Planning and Analysis
APP_PORT=8000

# Vertex AI settings
MODEL_NAME=gemini-2.5-pro
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-east1
GOOGLE_APPLICATION_CREDENTIALS=service-account.json

# Other settings...
```

### 3. Thiết lập Google Cloud credentials

Tạo file `service-account.json` với credentials của Google Cloud project.

### 4. Chạy server

```bash
python main.py
```

Server sẽ chạy tại `http://localhost:8000`

## API Endpoints

### 1. LiveChat (Multi-Agent)
- **URL**: `POST /ai/livechat`
- **Mô tả**: Endpoint chính sử dụng Multi-Agent System
- **Body**:
```json
{
  "conversationId": "conv_123",
  "sessionId": "session_456", 
  "message": "Lập kế hoạch học tiếng Anh 3 tháng",
  "channelId": "channel_789",
  "socialNetworkId": "social_101",
  "pageName": "Test Page"
}
```

### 2. DigitalChat (Classification)
- **URL**: `POST /ai/digitalchat` 
- **Mô tả**: Endpoint cho classification và routing ngắn gọn
- **Body**: Tương tự livechat

### 3. Prompt Setting
- **URL**: `POST /prompt/prompt-setting`
- **Mô tả**: Cấu hình prompt tùy chỉnh cho từng chat

## Ví dụ sử dụng

### Test với Python script

```bash
python test_multi_agents.py
```

### Test với curl

```bash
# Test Plan Agent
curl -X POST "http://localhost:8000/ai/livechat" \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test_conv",
    "sessionId": "test_session",
    "message": "Lập kế hoạch học Python trong 2 tháng",
    "channelId": "test_channel",
    "socialNetworkId": "test_social"
  }'

# Test Meta Agent  
curl -X POST "http://localhost:8000/ai/livechat" \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test_conv",
    "sessionId": "test_session", 
    "message": "Tại sao Python lại phổ biến?",
    "channelId": "test_channel",
    "socialNetworkId": "test_social"
  }'
```

## Cấu trúc thư mục

```
template/
├── agent/
│   ├── multi_agent_system.py    # Multi-Agent System chính
│   ├── histories.py             # Chat history management
│   ├── prompts.py              # System prompts
│   ├── meta/
│   │   ├── state.py            # Meta agent state
│   │   └── prompt.py           # Meta agent prompt
│   └── plan/
│       ├── state.py            # Plan agent state
│       └── prompts.py          # Plan agent prompts
├── router/v1/
│   ├── ai.py                   # API endpoints
│   └── get_prompt.py           # Prompt management
├── schemas/
│   └── model.py                # Pydantic models
└── configs/
    └── environments.py         # Environment settings
```

## Tính năng chính

1. **Auto-routing**: Tự động chọn agent phù hợp dựa trên input
2. **Memory management**: Lưu trữ lịch sử chat theo session
3. **Prompt customization**: Có thể tùy chỉnh prompt cho từng chat
4. **JSON response**: Hỗ trợ trả về JSON structured response
5. **Error handling**: Xử lý lỗi gracefully
6. **Multi-language**: Hỗ trợ cả tiếng Việt và tiếng Anh

## Troubleshooting

1. **Lỗi import**: Đảm bảo đã cài đặt tất cả dependencies
2. **Lỗi Google Cloud**: Kiểm tra file service-account.json và project ID
3. **Lỗi memory**: Kiểm tra thư mục `memories/` có quyền write
4. **Lỗi 500**: Xem logs để debug chi tiết

## Phát triển thêm

Để thêm agent mới:

1. Tạo class kế thừa từ `BaseAgent`
2. Implement các method `get_prompt()` và `process()`
3. Thêm routing logic vào `MultiAgentSystem._route_to_agent()`
4. Cập nhật test cases