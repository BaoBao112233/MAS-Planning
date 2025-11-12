// Global variables
let currentAudioUrl = null;
let voicesData = {}; // Store the complete voices structure
let currentLanguage = '';
let currentModel = '';
let currentVoice = '';

// DOM Elements
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const chatMessages = document.getElementById('chatMessages');
const loading = document.getElementById('loading');
const audioModal = document.getElementById('audioModal');
const audioPlayer = document.getElementById('audioPlayer');
const downloadBtn = document.getElementById('downloadBtn');

// Event listeners
messageInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// Load available voices from API
async function loadVoices() {
    try {
        console.log('🔍 Loading voices from API...');
        showNotification('Đang tải danh sách giọng nói...', 'info');
        
        const response = await fetch('/ai/voices');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        if (!result.success) {
            throw new Error('Failed to load voices');
        }
        
        voicesData = result.data;
        console.log('✅ Loaded voices:', result.summary);
        
        // Populate language dropdown
        populateLanguageDropdown();
        
        showNotification(`Đã tải ${result.summary.total_voices} giọng nói từ ${result.summary.total_languages} ngôn ngữ`, 'success');
    } catch (error) {
        console.error('Error loading voices:', error);
        showNotification('Lỗi khi tải danh sách giọng nói: ' + error.message, 'error');
    }
}

// Populate language dropdown
function populateLanguageDropdown() {
    const languageSelect = document.getElementById('languageSelect');
    languageSelect.innerHTML = '<option value="">-- Chọn ngôn ngữ --</option>';
    
    // Sort languages alphabetically
    const languages = Object.keys(voicesData).sort();
    
    languages.forEach(langCode => {
        const option = document.createElement('option');
        option.value = langCode;
        option.textContent = `${langCode}`;
        
        // Pre-select Vietnamese if available
        if (langCode === 'vi-VN') {
            option.selected = true;
            currentLanguage = langCode;
        }
        
        languageSelect.appendChild(option);
    });
    
    // If Vietnamese is preselected, populate models
    if (currentLanguage) {
        populateModelDropdown(currentLanguage);
    }
    
    languageSelect.disabled = false;
}

// Populate model dropdown based on selected language
function populateModelDropdown(languageCode) {
    const modelSelect = document.getElementById('modelSelect');
    const voiceSelect = document.getElementById('voiceSelect');
    
    if (!languageCode || !voicesData[languageCode]) {
        modelSelect.innerHTML = '<option value="">Select language first</option>';
        modelSelect.disabled = true;
        voiceSelect.innerHTML = '<option value="">Select model first</option>';
        voiceSelect.disabled = true;
        return;
    }
    
    modelSelect.innerHTML = '<option value="">-- Chọn model --</option>';
    const models = Object.keys(voicesData[languageCode]).sort();
    
    // Prioritize Neural2, WaveNet, then others
    const priorityOrder = ['Neural2', 'WaveNet', 'Chirp3-HD', 'Chirp-HD', 'Standard', 'Studio'];
    const sortedModels = models.sort((a, b) => {
        const aIndex = priorityOrder.indexOf(a);
        const bIndex = priorityOrder.indexOf(b);
        if (aIndex === -1 && bIndex === -1) return a.localeCompare(b);
        if (aIndex === -1) return 1;
        if (bIndex === -1) return -1;
        return aIndex - bIndex;
    });
    
    sortedModels.forEach((model, index) => {
        const option = document.createElement('option');
        option.value = model;
        option.textContent = model;
        
        // Pre-select Neural2 if available for Vietnamese
        if (languageCode === 'vi-VN' && model === 'Neural2') {
            option.selected = true;
            currentModel = model;
        }
        
        modelSelect.appendChild(option);
    });
    
    modelSelect.disabled = false;
    
    // If model is preselected, populate voices
    if (currentModel) {
        populateVoiceDropdown(languageCode, currentModel);
    }
}

// Populate voice dropdown based on selected language and model
function populateVoiceDropdown(languageCode, model) {
    const voiceSelect = document.getElementById('voiceSelect');
    
    if (!languageCode || !model || !voicesData[languageCode] || !voicesData[languageCode][model]) {
        voiceSelect.innerHTML = '<option value="">Select model first</option>';
        voiceSelect.disabled = true;
        return;
    }
    
    voiceSelect.innerHTML = '<option value="">-- Chọn giọng nói --</option>';
    const voices = voicesData[languageCode][model];
    
    // Sort by gender (FEMALE first, then MALE)
    const sortedVoices = voices.sort((a, b) => {
        if (a.gender === b.gender) return a.name.localeCompare(b.name);
        if (a.gender === 'FEMALE') return -1;
        if (b.gender === 'FEMALE') return 1;
        return a.gender.localeCompare(b.gender);
    });
    
    sortedVoices.forEach((voice, index) => {
        const option = document.createElement('option');
        option.value = voice.voice_name;  // Use full voice_name for API
        const genderIcon = voice.gender === 'FEMALE' ? '👩' : voice.gender === 'MALE' ? '👨' : '🧑';
        option.textContent = `${genderIcon} ${voice.name} (${voice.gender})`;  // Display short name
        
        // Pre-select first voice for Vietnamese Neural2
        if (languageCode === 'vi-VN' && model === 'Neural2' && index === 0) {
            option.selected = true;
            currentVoice = voice.voice_name;
        }
        
        voiceSelect.appendChild(option);
    });
    
    voiceSelect.disabled = false;
}

// Handle language selection change
document.addEventListener('DOMContentLoaded', function() {
    const languageSelect = document.getElementById('languageSelect');
    const modelSelect = document.getElementById('modelSelect');
    const voiceSelect = document.getElementById('voiceSelect');
    
    languageSelect.addEventListener('change', function() {
        const selectedLanguage = this.value;
        currentLanguage = selectedLanguage;
        currentModel = '';
        currentVoice = '';
        
        console.log('🌍 Language changed:', selectedLanguage);
        
        if (selectedLanguage) {
            populateModelDropdown(selectedLanguage);
            showNotification(`Ngôn ngữ đã chọn: ${selectedLanguage}`, 'info');
        } else {
            modelSelect.innerHTML = '<option value="">Select language first</option>';
            modelSelect.disabled = true;
            voiceSelect.innerHTML = '<option value="">Select model first</option>';
            voiceSelect.disabled = true;
        }
    });
    
    modelSelect.addEventListener('change', function() {
        const selectedModel = this.value;
        currentModel = selectedModel;
        currentVoice = '';
        
        console.log('🎨 Model changed:', selectedModel);
        
        if (selectedModel && currentLanguage) {
            populateVoiceDropdown(currentLanguage, selectedModel);
            showNotification(`Model đã chọn: ${selectedModel}`, 'info');
        } else {
            voiceSelect.innerHTML = '<option value="">Select model first</option>';
            voiceSelect.disabled = true;
        }
    });
    
    voiceSelect.addEventListener('change', function() {
        const selectedVoice = this.value;
        currentVoice = selectedVoice;
        
        console.log('🎤 Voice changed:', selectedVoice);
        
        if (selectedVoice) {
            showNotification(`Giọng nói đã chọn: ${selectedVoice}`, 'success');
        }
    });
    
    // Load voices on page load
    loadVoices();
});

// Send message function
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    const sessionId = document.getElementById('sessionId').value;
    const conversationId = document.getElementById('conversationId').value;
    const token = document.getElementById('token').value;
    
    // Get selected voice details
    const voice = currentVoice || 'vi-VN-Neural2-A'; // Fallback to default
    const language = currentLanguage || 'vi-VN';

    console.log('🎤 Selected voice:', voice);
    console.log('🌍 Selected language:', language);
    console.log('📤 Request data:', { conversationId, sessionId, token, message, voice });

    // Add user message to chat
    addMessage(message, 'user');
    
    // Clear input and disable send button
    messageInput.value = '';
    sendButton.disabled = true;
    showLoading(true);

    try {
        // Prepare request data
        const requestData = {
            conversationId: conversationId,
            sessionId: sessionId,
            token: token,
            message: message,
            voice: voice,
            language_code: language  // Send language code to backend
        };

        console.log('🚀 Sending request with voice:', requestData.voice);
        console.log('🌍 Sending request with language_code:', requestData.language_code);

        // Send request to API
        const response = await fetch('/ai/chat/text', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        
        // Add bot response to chat
        addMessage(data.response, 'bot', data.audio_file_url, voice, language, currentModel);

        // Show success notification
        showNotification('Tin nhắn đã được gửi thành công!', 'success');

    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('Xin lỗi, đã có lỗi xảy ra khi xử lý tin nhắn của bạn. Vui lòng thử lại.', 'bot');
        showNotification('Lỗi khi gửi tin nhắn: ' + error.message, 'error');
    } finally {
        sendButton.disabled = false;
        showLoading(false);
    }
}

// Add message to chat
function addMessage(text, sender, audioUrl = null, voiceName = null, languageCode = null, modelType = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    
    const icon = sender === 'user' ? 'fas fa-user' : 'fas fa-robot';
    
    let audioControls = '';
    if (audioUrl && sender === 'bot') {
        const voiceInfo = voiceName && languageCode && modelType 
            ? `Language: ${languageCode} | Model: ${modelType} | Voice: ${voiceName.split('-').pop()}`
            : voiceName || 'Default Voice';
            
        audioControls = `
            <div class="voice-indicator">
                <i class="fas fa-microphone-alt"></i>
                <span>${voiceInfo}</span>
            </div>
            <div class="audio-controls-inline">
                <button class="audio-btn" onclick="playInlineAudio('${audioUrl}')">
                    <i class="fas fa-play"></i> Phát Audio
                </button>
                <button class="audio-btn" onclick="openAudioModal('${audioUrl}')">
                    <i class="fas fa-volume-up"></i> Xem Audio
                </button>
                <button class="audio-btn" onclick="downloadAudio('${audioUrl}')">
                    <i class="fas fa-download"></i> Tải về
                </button>
            </div>
        `;
    }
    
    messageDiv.innerHTML = `
        <div class="message-content">
            <i class="${icon}"></i>
            <div class="text">
                ${text}
                ${audioControls}
            </div>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Show/hide loading
function showLoading(show) {
    loading.style.display = show ? 'block' : 'none';
}

// Play audio inline
function playInlineAudio(audioUrl) {
    const audio = new Audio(audioUrl);
    audio.play().catch(error => {
        console.error('Error playing audio:', error);
        showNotification('Không thể phát audio', 'error');
    });
}

// Open audio modal
function openAudioModal(audioUrl) {
    currentAudioUrl = audioUrl;
    audioPlayer.src = audioUrl;
    audioModal.style.display = 'flex';
    
    // Set download button
    downloadBtn.onclick = () => downloadAudio(audioUrl);
}

// Close audio modal
function closeAudioModal() {
    audioModal.style.display = 'none';
    audioPlayer.pause();
    currentAudioUrl = null;
}

// Play audio in modal
function playAudio() {
    if (audioPlayer.src) {
        audioPlayer.play().catch(error => {
            console.error('Error playing audio:', error);
            showNotification('Không thể phát audio', 'error');
        });
    }
}

// Download audio file
function downloadAudio(audioUrl) {
    try {
        // Create a temporary anchor element
        const link = document.createElement('a');
        link.href = audioUrl;
        
        // Extract filename from URL or create a default name
        const urlParts = audioUrl.split('/');
        const filename = urlParts[urlParts.length - 1] || `audio_${new Date().getTime()}.wav`;
        
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        showNotification('Đang tải file audio...', 'success');
    } catch (error) {
        console.error('Error downloading audio:', error);
        showNotification('Lỗi khi tải audio: ' + error.message, 'error');
    }
}

// Show notification
function showNotification(message, type = 'info') {
    // Remove existing notifications
    const existingNotifications = document.querySelectorAll('.notification');
    existingNotifications.forEach(notification => notification.remove());
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <i class="fas ${getNotificationIcon(type)}"></i>
            <span>${message}</span>
            <button class="notification-close" onclick="this.parentElement.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    
    // Add notification styles
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${getNotificationColor(type)};
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 1001;
        animation: slideInRight 0.3s ease;
        max-width: 400px;
    `;
    
    document.body.appendChild(notification);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

function getNotificationIcon(type) {
    switch (type) {
        case 'success': return 'fa-check-circle';
        case 'error': return 'fa-exclamation-circle';
        case 'warning': return 'fa-exclamation-triangle';
        default: return 'fa-info-circle';
    }
}

function getNotificationColor(type) {
    switch (type) {
        case 'success': return '#28a745';
        case 'error': return '#dc3545';
        case 'warning': return '#ffc107';
        default: return '#17a2b8';
    }
}

// Close modal when clicking outside
audioModal.addEventListener('click', function(e) {
    if (e.target === audioModal) {
        closeAudioModal();
    }
});

// Add notification animation styles
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    .notification-content {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .notification-close {
        background: none;
        border: none;
        color: white;
        cursor: pointer;
        padding: 2px;
        border-radius: 2px;
        margin-left: auto;
    }
    
    .notification-close:hover {
        background: rgba(255,255,255,0.2);
    }
`;
document.head.appendChild(style);

// Initialize the app
document.addEventListener('DOMContentLoaded', function() {
    console.log('MAS Planning Chat Demo initialized');
    
    // Focus on message input
    messageInput.focus();
    
    // Generate random session IDs if empty
    if (!document.getElementById('sessionId').value) {
        document.getElementById('sessionId').value = `session-${Math.random().toString(36).substr(2, 9)}`;
    }
    
    if (!document.getElementById('conversationId').value) {
        document.getElementById('conversationId').value = `conv-${Math.random().toString(36).substr(2, 9)}`;
    }
});

// Debug function for testing - can be called from browser console
window.testVoiceSelection = function() {
    const languageSelect = document.getElementById('languageSelect');
    const modelSelect = document.getElementById('modelSelect');
    const voiceSelect = document.getElementById('voiceSelect');
    
    console.log('=== Voice Selection Debug ===');
    console.log('Language:', {
        index: languageSelect.selectedIndex,
        value: languageSelect.value,
        text: languageSelect.options[languageSelect.selectedIndex]?.text
    });
    console.log('Model:', {
        index: modelSelect.selectedIndex,
        value: modelSelect.value,
        text: modelSelect.options[modelSelect.selectedIndex]?.text
    });
    console.log('Voice:', {
        index: voiceSelect.selectedIndex,
        value: voiceSelect.value,
        text: voiceSelect.options[voiceSelect.selectedIndex]?.text
    });
    console.log('Current Selection:', {
        language: currentLanguage,
        model: currentModel,
        voice: currentVoice
    });
    console.log('Voices Data:', voicesData);
    
    return {
        language: currentLanguage,
        model: currentModel,
        voice: currentVoice
    };
};

console.log('✅ Voice debug function loaded. Type testVoiceSelection() in console to debug.');