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
└── postgres/redis/     # Database configs
```

## 📚 Tài liệu

- [API Documentation](API_README.md)
- [Vertex AI Setup](VERTEX_AI_SETUP.md)
- [Deployment Guide](DEPLOYMENT_SUCCESS.md)

## 🔧 Sử dụng

### Chat với bot

```python
import requests

response = requests.post("http://localhost:8000/ai/livechat", json={
    "conversationId": "123",
    "sessionId": "456",
    "message": "Tôi cần hỗ trợ CRM",
    "channelId": "1",
    "socialNetworkId": "1",
    "pageName": "Fanpage Name"
})
print(response.json())
```

### Cấu hình prompt tùy chỉnh

```bash
curl -X POST "http://localhost:8000/ai/prompt-setting" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": 1,
    "name": "CRM Bot",
    "system_prompt": "Bạn là trợ lý CRM chuyên nghiệp",
    "temperature": 0.2
  }'
```

## 🐳 Docker

```bash
# Development
docker-compose up --build

# Production
docker-compose -f docker-compose.prod.yml up -d
```

## 🤝 Đóng góp

1. Fork project
2. Tạo feature branch
3. Commit changes
4. Push và tạo PR

## 📞 Liên hệ

[BaoBao112233](mailto:kevinbao15072002@gmail.com)
