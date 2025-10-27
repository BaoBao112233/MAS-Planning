# 🚀 Demo Instructions - MAS Planning Chat UI

## Quick Start

### 1. Khởi chạy
```bash
cd /home/baobao/Projects/MAS-Planning
conda activate mas-env
python main.py
```

### 2. Truy cập
Mở browser: `http://localhost:9000`

## 🎯 Test Cases

### **Test 1: Simple Greeting**
```
Input: "Hello" hoặc "Xin chào"
Expected: Direct response với audio file
```

### **Test 2: Planning Request**
```
Input: "Camera detected 1 person in the living room. Temperature: 20C. Create plan."
Expected: 3 plan options với audio
```

### **Test 3: Plan Selection**
```
Input: "Plan 1" hoặc "1"
Expected: Execute selected plan với audio
```

### **Test 4: Device Control**
```
Input: "Turn on the lights"
Expected: Tool agent response với audio
```

## 🎵 Audio Features Test

### **Phát Audio Inline**
1. Gửi bất kỳ tin nhắn nào
2. Chờ bot response
3. Click nút "🔊 Phát Audio"
4. ✅ Audio should play immediately

### **Xem Audio Modal**
1. Click nút "🔊 Xem Audio" 
2. ✅ Modal popup opens
3. ✅ Audio player controls visible
4. Click "Play Again" để test
5. Click outside modal để close

### **Download Audio**
1. Click nút "💾 Tải về" (inline hoặc trong modal)
2. ✅ File `response_xxx.wav` should download
3. ✅ Check file can be played

## 🛠️ Configuration Test

### **Change Session/Conversation ID**
1. Modify Session ID và Conversation ID
2. Send message
3. ✅ New conversation should start
4. ✅ Log should show new IDs

### **Token Test**
1. Get real token: `http://localhost:9000/token?user_phone=0966897557&user_password=abc123`
2. Copy token vào Token field
3. Send planning request
4. ✅ Should work with real MCP tools

## 🐛 Troubleshooting

### **Audio không phát**
- Check browser console for errors
- Verify ElevenLabs API is working
- Check network requests in DevTools

### **UI không responsive**
- Check static files are loading
- Verify CSS/JS files in Network tab
- Try hard refresh (Ctrl+F5)

### **API errors**
- Check server logs
- Verify endpoints in /docs
- Test with Postman/curl first

## ✨ Features Confirmed Working

✅ **Chat Interface**
- Responsive design
- Message sending/receiving
- Loading indicators
- Error notifications

✅ **Audio Integration**
- Text-to-Speech generation
- Audio playback controls
- File download functionality
- Modal popup player

✅ **API Integration**
- POST /ai/chat/text endpoint
- JSON request/response handling
- Error handling
- Loading states

✅ **Configuration**
- Session/Conversation management
- Token authentication
- Dynamic ID generation

✅ **Multi-Agent Routing**
- Direct responses for greetings
- Plan Agent for planning requests
- Tool Agent for device control
- Proper confidence scoring

## 🎨 UI/UX Features

✅ **Modern Design**
- Gradient backgrounds
- Glass morphism effects
- Smooth animations
- Font Awesome icons

✅ **Responsive Layout**
- Mobile-friendly
- Adaptive grid
- Touch-optimized buttons
- Flexible containers

✅ **Interactive Elements**
- Hover effects
- Click animations
- Focus states
- Loading spinners

## 📱 Mobile Test

1. Open on mobile browser
2. ✅ Layout adapts properly
3. ✅ Touch interactions work
4. ✅ Audio controls accessible
5. ✅ Modal responsive

## 🔄 End-to-End Flow

1. **Open UI** → Loading screen
2. **Send greeting** → Direct response + audio
3. **Planning request** → Plan options + audio  
4. **Select plan** → Execution details + audio
5. **Download audio** → File saved locally
6. **New conversation** → Fresh session

## 📊 Performance Notes

- Initial load: ~2-3 seconds
- Message response: ~5-10 seconds (includes AI processing)
- Audio generation: ~1-2 seconds (ElevenLabs)
- File download: Instant

## 🎉 Demo Complete!

UI đã sẵn sàng để demo với đầy đủ tính năng:
- ✅ Text chat với AI responses
- ✅ Text-to-Speech audio generation  
- ✅ Audio playback và download
- ✅ Multi-agent routing
- ✅ Beautiful, responsive UI
- ✅ Error handling và notifications