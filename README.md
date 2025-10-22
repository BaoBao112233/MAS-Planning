# CRM Oxii Chatbot

Chatbot AI thông minh cho CRM, sử dụng Google Cloud Vertex AI và LangChain.

## 🚀 Cài đặt nhanh

### 1. Sao chép và cài đặt

```bash
git clone https://github.com/BaoBao112233/CRM-Oxii-Chatbot.git
cd CRM-Oxii-Chatbot
pip install -r requirements.txt
```

### 2. Cấu hình Google Cloud

```bash
# Tạo service account và tải key
cp .env.example .env
# Chỉnh sửa .env với thông tin GCP của bạn
```

### 3. Chạy ứng dụng

```bash
python main.py
```

### 4. Test

```bash
curl -X POST "http://localhost:8000/ai/livechat" \
  -H "Content-Type: application/json" \
  -d '{"conversationId": "1", "sessionId": "1", "message": "Xin chào", "channelId": "1", "socialNetworkId": "1", "pageName": "Name fanpage"}'
```

## 📋 Yêu cầu

- Python 3.8+
- Google Cloud Project với Vertex AI API
- Service Account với quyền `roles/aiplatform.user`

## 🏗️ Kiến trúc

```
├── main.py              # Entry point
├── template/
│   ├── agent/          # AI agent logic
│   ├── configs/        # Environment configs
│   ├── router/         # API endpoints
│   └── schemas/        # Data models
├── memories/           # Chat history
├── saved_prompt/       # Custom prompts
````markdown
# MAS-Planning — Multi-Agent Smart Home Planning

Hệ thống MAS-Planning là một project mẫu cho multi-agent automation (MetaAgent, ToolAgent, PlanAgent) dùng để lập kế hoạch và điều khiển thiết bị nhà thông minh qua MCP (Model Context Protocol). Dự án tích hợp Vertex AI (hoặc tương đương), LangGraph/StateGraph để điều phối luồng công việc giữa các agent.

Mục tiêu:
- Sinh kế hoạch ưu tiên từ input (ví dụ: camera phát hiện người)
- Phân rã kế hoạch thành các tasks
- Gửi tasks cho MetaAgent phân tích chi tiết
- ToolAgent gọi MCP tools để thực thi (bật/tắt thiết bị, điều hoà, play audio...)
- Theo dõi và báo cáo trạng thái (API upload / task status)

## 🚀 Quickstart (phát triển)

1) Clone repo và cài phụ thuộc

```bash
git clone https://github.com/BaoBao112233/MAS-Planning.git
cd MAS-Planning
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

2) Cấu hình môi trường

1. Copy file mẫu service account nếu dùng GCP:

```bash
cp service-account.json.example service-account.json
# Hoặc copy .env mẫu nếu có
```

- Mở `template/configs/environments.py` và thiết lập các biến môi trường cần thiết (hoặc dùng biến môi trường hệ thống):

  - `MCP_SERVER_URL` — URL MCP server (ví dụ: `http://localhost:9031`)
  - `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` — nếu dùng Vertex AI

3) Chạy server

```bash
python main.py
```

Server mặc định chạy trên `http://0.0.0.0:9000` (kiểm tra log khi khởi động).

4) Gửi thử một request chat / lên kế hoạch

```bash
curl -X POST "http://localhost:9000/ai/chat" \
  -H "Content-Type: application/json" \
  -d '{"conversationId":"test","sessionId":"s1","message":"Camera: 1 person in living room","channelId":"test","socialNetworkId":"test","pageName":"test"}'
```

Ứng dụng sẽ trả về các plan options; khi chọn một plan, hệ thống sẽ upload plan lên API (nếu `APIClient` được cấu hình) và bắt đầu gọi MetaAgent → ToolAgent để thực thi.

## ⚙️ Cấu trúc chính

```
.
├── main.py                  # Entry point (FastAPI server)
├── template/
│   ├── agent/
│   │   ├── plan/            # PlanAgent: lập kế hoạch & orchestration
│   │   ├── meta/            # MetaAgent: phân tích & tách nhiệm vụ
│   │   └── tool/            # ToolAgent: gọi MCP tools để thực thi
│   ├── configs/             # Biến môi trường và cấu hình
│   └── router/              # API endpoints (ví dụ: /ai/chat)
├── requirements-dev.txt     # Python deps cho dev
├── docker-compose.yml       # Compose dev/prod
└── service-account.json.example
```

## 🧭 Cấu hình quan trọng

- `template/configs/environments.py` — nơi đọc các biến môi trường.
- `MCP_SERVER_URL` — pointer tới MCP server (bắt buộc nếu muốn ToolAgent kết nối)
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` — dùng khi tích hợp Vertex AI

Thêm biến môi trường ví dụ (bash):

```bash
export MCP_SERVER_URL="http://localhost:9031"
export GOOGLE_CLOUD_PROJECT="your-gcp-project"
export GOOGLE_CLOUD_LOCATION="us-central1"
```

## 🧪 Testing & Development notes

- Khi phát triển, logs rất quan trọng: theo dõi `template.agent.plan`, `template.agent.tool`, `template.agent.meta` để debug luồng.
- Nếu `ToolAgent` báo `No MCP tools available`, kiểm tra `MCP_SERVER_URL` và chạy server MCP mô phỏng (repo không bao gồm MCP server — cần một mock hoặc local MCP service).
- Nếu gặp `asyncio.run() cannot be called from a running event loop`, đó là do gọi `asyncio.run()` trong môi trường đã có event loop (ví dụ uvicorn). Sửa bằng cách thay đổi khởi tạo async: sử dụng `asyncio.create_task()` từ context async hoặc initialisation được chạy trong startup event của FastAPI.

## ⚠️ Troubleshooting nhanh

- ToolAgent không load được tools: kiểm tra kết nối đến MCP server (URL, CORS, network)
- MetaAgent không trả đúng format XML: kiểm tra prompt trong `template/agent/meta/prompt.py` và xem response thực tế từ LLM
- Lặp vô hạn / deadlock: kiểm tra chỗ gọi `asyncio.run()` trong code; đổi sang `await` hoặc dùng startup event

## 🐳 Docker

Phát triển với docker-compose (nếu bạn có file compose cài sẵn):

```bash
docker-compose up --build
```

## 🔗 Tài liệu liên quan

- Xem `README_MULTI_AGENT.md` và `README.md` (nội bộ) cho hướng dẫn chi tiết hơn về từng agent.

## 🤝 Đóng góp

1. Fork repo
2. Tạo branch feature
3. Commit & PR

## 📞 Liên hệ

BaoBao — <kevinbao15072002@gmail.com>

````
