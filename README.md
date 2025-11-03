# MAS-Planning — Multi-Agent Smart Home Planning

Hệ thống MAS-Planning là một dự án multi-agent automation cho smart home sử dụng Model Context Protocol (MCP). Dự án tích hợp Google Cloud Vertex AI, LangGraph/StateGraph để điều phối luồng công việc giữa các agent: PlanAgent, MetaAgent, và ToolAgent.

## 🎯 Mục tiêu

- **Sinh kế hoạch thông minh**: Tạo kế hoạch ưu tiên từ input (camera phát hiện người, sensor data)
- **Phân rã nhiệm vụ**: MetaAgent phân tích và chia nhỏ kế hoạch thành các tasks cụ thể
- **Thực thi tự động**: ToolAgent gọi MCP tools để điều khiển thiết bị (đèn, điều hòa, loa...)
- **Theo dõi trạng thái**: API integration để upload plans và track task status
- **Workflow orchestration**: LangGraph StateGraph quản lý luồng giữa các agent

## 🚀 Quickstart

### 1. Setup môi trường

```bash
git clone https://github.com/BaoBao112233/MAS-Planning.git
cd MAS-Planning
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

### 2. Cấu hình environment variables

Copy và chỉnh sửa file environment:

```bash
cp .env.template .env
# Hoặc copy service account nếu dùng GCP
cp service-account.json.example service-account.json
```

Các biến quan trọng trong `.env`:

```bash
# Application
APP_NAME="MAS Planning System"
APP_DESC="Multi-Agent Smart Home Planning"
API_VERSION="1.0.0"
APP_PORT=9000

# Google Cloud (nếu dùng Vertex AI)
GOOGLE_CLOUD_PROJECT="your-project-id"
GOOGLE_CLOUD_LOCATION="us-central1"
MODEL_NAME="gemini-2.5-flash"

# MCP Server
MCP_SERVER_URL="http://localhost:9031"

# API Integration (optional)
API_BASE_URL="http://localhost:8080"
```

### 3. Chạy server

```bash
python main.py
```

Server mặc định chạy trên `http://0.0.0.0:9000`.

### 4. Test thử workflow

Tạo kế hoạch từ camera input:

```bash
curl -X POST "http://localhost:9000/ai/chat" \
  -H "Content-Type: application/json" \
  -d '{"conversationId":"test","sessionId":"s1","message":"Camera: 1 person in living room","channelId":"test","socialNetworkId":"test","pageName":"test"}'
```

Chọn plan (ví dụ chọn plan 2 - Convenience):

```bash
curl -X POST "http://localhost:9000/ai/chat" \
  -H "Content-Type: application/json" \
  -d '{"conversationId":"test","sessionId":"s1","message":"2","channelId":"test","socialNetworkId":"test","pageName":"test"}'
```

## 🏗️ Kiến trúc hệ thống

```text
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PlanAgent     │───▶│   MetaAgent     │───▶│   ToolAgent     │
│                 │    │                 │    │                 │
│ • Plan creation │    │ • Task analysis │    │ • MCP tools     │
│ • Orchestration │    │ • XML parsing   │    │ • Device control│
│ • API upload    │    │ • Context aware │    │ • Execution     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │     LangGraph State     │
                    │                         │
                    │ • Workflow control      │
                    │ • Agent communication  │
                    │ • State management     │
                    └─────────────────────────┘
```

### Cấu trúc thư mục

```text
.
├── main.py                     # FastAPI server entry point
├── template/
│   ├── agent/
│   │   ├── plan/              # PlanAgent - Plan creation & orchestration
│   │   │   ├── __init__.py    # Main PlanAgent class
│   │   │   ├── prompts.py     # Planning prompts
│   │   │   ├── state.py       # State definitions
│   │   │   └── utils.py       # Helper functions
│   │   ├── meta/              # MetaAgent - Task analysis
│   │   │   ├── __init__.py    # MetaAgent class
│   │   │   ├── prompt.py      # Meta analysis prompts
│   │   │   ├── state.py       # State management
│   │   │   └── utils.py       # XML parsing utilities
│   │   └── tool/              # ToolAgent - MCP tool execution
│   │       ├── __init__.py    # ToolAgent class
│   │       └── (MCP integration)
│   ├── configs/
│   │   └── environments.py    # Environment configuration
│   ├── router/
│   │   └── v1/
│   │       └── ai.py          # API endpoints
│   ├── message/
│   │   └── message.py         # Message classes
│   └── schemas/
│       └── model.py           # Data models
├── requirements-dev.txt       # Python dependencies
├── docker-compose.yml         # Docker setup
├── service-account.json       # GCP credentials
└── .env                       # Environment variables
```

## 🔧 Workflow chi tiết

1. **Input Processing**: User gửi message qua `/ai/chat` endpoint
2. **Plan Generation**: PlanAgent tạo 3 kế hoạch ưu tiên (Security, Convenience, Energy)
3. **User Selection**: User chọn plan (1, 2, hoặc 3)
4. **API Upload**: Plan được upload lên external API (nếu cấu hình)
5. **Task Execution**:
   - MetaAgent phân tích từng task
   - ToolAgent thực thi qua MCP tools
   - Cập nhật task status qua API
6. **Completion**: Báo cáo kết quả và hoàn thành plan

## 📋 Requirements

- **Python**: 3.8+
- **Google Cloud**: Project với Vertex AI API enabled
- **MCP Server**: Running trên URL được cấu hình
- **Service Account**: Với quyền `roles/aiplatform.user` (nếu dùng GCP)

## 🧭 Configuration Reference

### Environment Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `APP_NAME` | Application name | "MAS Planning System" | Yes |
| `APP_PORT` | Server port | 9000 | Yes |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID | "my-project-123" | Yes (if using Vertex AI) |
| `GOOGLE_CLOUD_LOCATION` | GCP region | "us-central1" | Yes (if using Vertex AI) |
| `MODEL_NAME` | LLM model | "gemini-2.5-flash" | Yes |
| `MCP_SERVER_URL` | MCP server endpoint | `http://localhost:9031` | Yes |
| `API_BASE_URL` | External API for plan upload | `http://localhost:8080` | No |

### Service Account Setup (GCP)

1. Tạo service account trong GCP Console
2. Gán role `AI Platform User` (`roles/aiplatform.user`)
3. Download JSON key file
4. Copy thành `service-account.json`

## 🧪 Development & Testing

### Debugging

Theo dõi logs để debug workflow:

```bash
# Tăng log level nếu cần
export PYTHONPATH=/home/baobao/Projects/MAS-Planning
python main.py --log-level DEBUG
```

Key log patterns:

- `template.agent.plan` - PlanAgent operations
- `template.agent.meta` - MetaAgent analysis
- `template.agent.tool` - ToolAgent execution

### Troubleshooting

**❌ "No MCP tools available"**

- Kiểm tra `MCP_SERVER_URL` trong environment
- Đảm bảo MCP server đang chạy
- Test connectivity: `curl http://localhost:9031/health`

**❌ "LLM not initialized"**

- Kiểm tra GCP credentials và service account
- Xác nhận `GOOGLE_CLOUD_PROJECT` đúng
- Thử test Vertex AI access riêng biệt

**❌ "asyncio.run() cannot be called from running event loop"**

- Do conflict giữa uvicorn và asyncio
- Fix bằng cách dùng startup events thay vì `asyncio.run()`

**❌ "XML parse error" từ MetaAgent**

- Kiểm tra prompt format trong `template/agent/meta/prompt.py`
- LLM response phải chứa valid XML tags

### Mock MCP Server

Để test mà không cần MCP server thật:

```python
# Tạo file mock_mcp.py
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/sse")  
def sse():
    return {"url": "http://localhost:9031/messages/"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9031)
```

## 🐳 Docker

Development với docker-compose:

```bash
docker-compose up --build
```

Production deployment:

```bash
docker-compose -f docker-compose.prod.yml up -d
```

## 📚 API Documentation

### POST `/ai/chat`

**Request:**

```json
{
  "conversationId": "string",
  "sessionId": "string", 
  "message": "string",
  "channelId": "string",
  "socialNetworkId": "string",
  "pageName": "string"
}
```

**Response (Plan Options):**

```json
{
  "plan_options": {
    "security_plan": ["Task 1...", "Task 2..."],
    "convenience_plan": ["Task 1...", "Task 2..."],
    "energy_plan": ["Task 1...", "Task 2..."]
  },
  "needs_user_selection": true
}
```

**Response (Execution Result):**

```json
{
  "plan": ["Selected tasks..."],
  "execution_results": [
    {
      "task_number": 1,
      "task": "Task description",
      "status": "completed",
      "result": "Success message"
    }
  ],
  "output": "Execution summary"
}
```

## 🔗 Tài liệu liên quan

- [Model Context Protocol (MCP)](https://docs.anthropic.com/mcp)
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)
- [Google Cloud Vertex AI](https://cloud.google.com/vertex-ai/docs)

## 🤝 Contributing

1. Fork repository
2. Tạo feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push branch: `git push origin feature/amazing-feature`
5. Tạo Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/MAS-Planning.git
cd MAS-Planning

# Create development environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Install pre-commit hooks (optional)
pre-commit install
```

## 📞 Support & Contact

- **Author**: BaoBao112233
- **Email**: [kevinbao15072002@gmail.com](mailto:kevinbao15072002@gmail.com)
- **GitHub**: [https://github.com/BaoBao112233/MAS-Planning](https://github.com/BaoBao112233/MAS-Planning)
- **Issues**: [GitHub Issues](https://github.com/BaoBao112233/MAS-Planning/issues)

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.