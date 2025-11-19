# Audio Endpoints Guide

## Tổng quan

Hệ thống đã được cập nhật với hai endpoint mới để hỗ trợ xử lý audio:

1. `/ai/chat/text` - Chat với text và nhận kết quả có audio
2. `/ai/chat/audio` - Chat với audio và nhận kết quả có cả text và audio

## Endpoint Details

### 1. POST `/ai/chat/text`

Xử lý tin nhắn text và trả về response cùng với file audio.

**Request Body:**
```json
{
    "conversationId": "string",
    "sessionId": "string", 
    "token": "string",
    "message": "string"
}
```

**Response:**
```json
{
    "sessionId": "string",
    "response": "string",
    "error_status": "success|error",
    "audio_file_url": "/ai/download/audio/{filename}.wav"
}
```

### 2. POST `/ai/chat/audio`

Xử lý file audio, chuyển đổi thành text, xử lý qua chatbot, và trả về kết quả có cả text và audio.

**Request (multipart/form-data):**
- `sessionId`: string
- `conversationId`: string  
- `token`: string
- `audio_file`: file (audio/wav)

**Response:**
```json
{
    "sessionId": "string",
    "transcribed_text": "string",
    "response": "string", 
    "error_status": "success|error",
    "audio_file_url": "/ai/download/audio/{filename}.wav"
}
```

### 3. GET `/ai/download/audio/{filename}`

Tải file audio đã được tạo.

**Response:** File audio WAV

## Text-to-Speech Integration

Hệ thống sử dụng Google Cloud Text-to-Speech API để:

- **Speech-to-Text**: Chuyển đổi file audio thành text (Google Cloud Speech-to-Text)
- **Text-to-Speech**: Chuyển đổi response text thành file audio (Google Cloud TTS)

### Cấu hình

- **Google Cloud API Key**: Configured in environment variables
- **Voice Options**: Multiple language voices available via `/ai/voices` endpoint
- **Default Voice**: `vi-VN-Neural2-A` (Vietnamese) or `en-US-Neural2-A` (English)
- **Audio Format**: MP3 format for TTS output

## File Management

- File audio tạm thời được lưu trong `/tmp/`
- File sẽ được tự động xóa sau 1 giờ
- Format file đầu ra: `response_{sessionId}_{timestamp}.wav`

## Error Handling

- Nếu không thể tạo audio, endpoint `/chat/text` vẫn trả về text response
- Endpoint `/chat/audio` sẽ trả về lỗi nếu không thể xử lý audio input
- Tất cả lỗi đều được log chi tiết

## Yêu cầu hệ thống

### Dependencies mới:
- `httpx>=0.25.0` - HTTP client async
- `aiofiles>=23.0.0` - File I/O async

### Permissions:
- Quyền ghi vào thư mục `/tmp/`

## Ví dụ sử dụng

### Text Chat với Audio Response

```bash
curl -X POST "http://localhost:8000/ai/chat/text" \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "conv123",
    "sessionId": "session123",
    "token": "your_token",
    "message": "Xin chào, bạn có thể giúp tôi lập kế hoạch du lịch không?"
  }'
```

### Audio Chat

```bash
curl -X POST "http://localhost:8000/ai/chat/audio" \
  -F "sessionId=session123" \
  -F "conversationId=conv123" \
  -F "token=your_token" \
  -F "audio_file=@recording.wav"
```

### Download Audio

```bash
curl -X GET "http://localhost:8000/ai/download/audio/response_session123_20241027_101530.wav" \
  --output response.wav
```

## Troubleshooting

### Lỗi thường gặp:

1. **"Failed to generate speech"**: Kiểm tra Google Cloud API credentials và quota
2. **"Could not transcribe audio"**: Đảm bảo file audio có định dạng đúng
3. **"Audio file not found"**: File có thể đã bị xóa sau 1 giờ

### Logs:

Tất cả hoạt động đều được log với các emoji để dễ theo dõi:
- 🎵 Audio processing
- 📝 Text processing  
- 💾 Caching
- 🗑️ File cleanup