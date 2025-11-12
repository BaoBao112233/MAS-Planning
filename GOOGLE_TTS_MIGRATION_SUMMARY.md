# Google Cloud TTS Migration Summary

## Overview
Successfully migrated the MAS Planning Chat Demo from Groq PlayAI TTS to Google Cloud Text-to-Speech with hierarchical voice selection.

## Changes Made

### 1. Backend Changes

#### `/home/baobao/Projects/MAS-Planning/template/utils/tts.py`
- **Removed**: Groq PlayAI dependency and `AVAILABLE_VOICES` list
- **Added**: `get_available_voices()` function to fetch voices from Google Cloud TTS API
  - Returns hierarchical structure: `{language_code: {model_type: [{name, gender, natural_sample_rate_hertz}]}}`
  - Implements voice caching with `_VOICES_CACHE` to avoid repeated API calls
  - Automatically categorizes voices into types: Chirp3-HD, Chirp-HD, Neural2, WaveNet, Studio, Standard, News, Polyglot, Casual
- **Updated**: `text_to_speech_with_voice()` function
  - Changed signature: now accepts `voice_name` and `language_code` parameters instead of single `voice` parameter
  - Improved error handling with specific HTTP status codes
  - Enhanced logging with emoji indicators
- **Kept**: `speech_to_text()` function unchanged (already uses Google Speech-to-Text)

#### `/home/baobao/Projects/MAS-Planning/template/router/v1/ai.py`
- **Added**: `GET /ai/voices` endpoint
  - Returns complete voice hierarchy from Google Cloud TTS
  - Includes summary statistics (total_languages, total_voices)
  - Comprehensive error handling and logging
- **Updated**: `POST /ai/chat/text` endpoint
  - Changed voice handling: `voice_name` and `language_code` parameters
  - Default: `vi-VN-Neural2-A` for Vietnamese
  - Updated logging to show both voice and language
- **Updated**: `POST /ai/chat/audio` endpoint
  - Same voice parameter updates as text endpoint
  - Maintains backward compatibility with default Vietnamese voices

### 2. Frontend Changes

#### `/home/baobao/Projects/MAS-Planning/static/index.html`
- **Replaced**: Single voice dropdown with 3 cascading dropdowns
  - Language selector (`languageSelect`)
  - Model selector (`modelSelect`)
  - Voice selector (`voiceSelect`)
- **Added**: `.voice-config` class for styling multiple dropdowns
- **Updated**: Cache busting version from `v2` to `v3`

#### `/home/baobao/Projects/MAS-Planning/static/script.js`
- **Added Global Variables**:
  - `voicesData`: Stores complete voice hierarchy
  - `currentLanguage`, `currentModel`, `currentVoice`: Track selections
- **Added Functions**:
  - `loadVoices()`: Fetches voices from `/ai/voices` endpoint on page load
  - `populateLanguageDropdown()`: Fills language dropdown, pre-selects Vietnamese
  - `populateModelDropdown()`: Fills model dropdown based on language, prioritizes Neural2/WaveNet
  - `populateVoiceDropdown()`: Fills voice dropdown based on language+model, sorts by gender
- **Updated Functions**:
  - `sendMessage()`: Now sends `voice` (full voice name) instead of old format
  - `addMessage()`: Enhanced voice indicator showing "Language: {lang} | Model: {model} | Voice: {voice}"
- **Added Event Listeners**: Cascading logic for all three dropdowns
- **Updated Debug Function**: `testVoiceSelection()` now shows all three selections and data structure

#### `/home/baobao/Projects/MAS-Planning/static/style.css`
- **Added**: `.voice-config` class for voice selector container
- **Added**: `.voice-selectors` grid layout
  - 3 columns on desktop
  - 1 column on mobile (responsive)
  - 10px gap between dropdowns
- **Added**: `select:disabled` styling for disabled state (grayed out, cursor not-allowed)

## Voice Selection Flow

1. **Page Load**:
   - JavaScript calls `/ai/voices` endpoint
   - API fetches voices from Google Cloud TTS
   - Populates language dropdown
   - Pre-selects Vietnamese (`vi-VN`)

2. **Language Selection**:
   - User selects language (e.g., `vi-VN`)
   - Model dropdown populated with available models for that language
   - Models sorted by priority: Neural2 → WaveNet → Chirp3-HD → Others
   - Vietnamese: Pre-selects Neural2

3. **Model Selection**:
   - User selects model (e.g., `Neural2`)
   - Voice dropdown populated with voices for that language+model combination
   - Voices sorted by gender (FEMALE → MALE → NEUTRAL)
   - Vietnamese Neural2: Pre-selects first voice (typically `vi-VN-Neural2-A`)

4. **Message Sending**:
   - User sends message
   - Frontend sends: `voice: "vi-VN-Neural2-A"` (full voice name)
   - Backend uses: `voice_name="vi-VN-Neural2-A"`, `language_code="vi-VN"`
   - TTS generates audio with selected voice

5. **Voice Indicator**:
   - Bot message displays: "Language: vi-VN | Model: Neural2 | Voice: A (FEMALE)"
   - Clear visibility of exact voice configuration used

## Available Voice Types (Google Cloud TTS)

### Vietnamese (`vi-VN`)
- **Neural2**: `vi-VN-Neural2-A` (FEMALE), `vi-VN-Neural2-D` (MALE)
- **WaveNet**: `vi-VN-Wavenet-A`, `vi-VN-Wavenet-B`, `vi-VN-Wavenet-C`, `vi-VN-Wavenet-D`
- **Standard**: `vi-VN-Standard-A`, `vi-VN-Standard-B`, `vi-VN-Standard-C`, `vi-VN-Standard-D`

### English (US) - `en-US`
- **Chirp3-HD**: 30+ voices (Achernar, Achird, Algenib, etc.)
- **Neural2**: 10+ voices (A, C, D, E, F, G, H, I, J)
- **WaveNet**: 10+ voices
- **Studio**: O, Q
- **News**: K, L, N
- **Standard**: A-J

### Other Languages
- 40+ languages supported
- Each language has multiple models and voices
- See [Google Cloud TTS Documentation](https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types)

## Testing Checklist

- [ ] API endpoint `/ai/voices` returns valid voice data
- [ ] Language dropdown populates with all languages
- [ ] Model dropdown updates when language changes
- [ ] Voice dropdown updates when model changes
- [ ] Disabled states work correctly (model disabled until language selected, etc.)
- [ ] Pre-selection works: Vietnamese → Neural2 → First voice
- [ ] Audio generation uses correct voice
- [ ] Voice indicator displays correct information
- [ ] Logs show correct language_code and voice_name
- [ ] Browser hard reload (Ctrl+Shift+R) loads new UI
- [ ] Mobile responsive layout (1 column on small screens)
- [ ] Debug function `testVoiceSelection()` works in console

## Deployment Steps

1. **Restart Docker Container**:
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

2. **Check Logs**:
   ```bash
   docker-compose logs -f
   ```
   - Look for: "🔍 Fetching available voices from Google Cloud TTS..."
   - Should see: "✅ Fetched X voices across Y languages"

3. **Test API Endpoint**:
   ```bash
   curl http://localhost:9000/ai/voices | jq '.summary'
   ```
   - Should return: `{"total_languages": X, "total_voices": Y}`

4. **Test UI**:
   - Open: http://localhost:9000/static/index.html
   - Hard reload: Ctrl+Shift+R (clear cache)
   - Check: 3 dropdowns visible (Language | Model | Voice)
   - Check: Vietnamese pre-selected
   - Send message and verify audio generation

5. **Debug**:
   - Open browser console (F12)
   - Type: `testVoiceSelection()`
   - Should show current selection and voice data structure

## API Changes

### New Endpoint
```
GET /ai/voices
```

**Response**:
```json
{
  "success": true,
  "data": {
    "vi-VN": {
      "Neural2": [
        {
          "name": "vi-VN-Neural2-A",
          "gender": "FEMALE",
          "natural_sample_rate_hertz": 24000
        }
      ]
    }
  },
  "summary": {
    "total_languages": 40,
    "total_voices": 500
  }
}
```

### Updated Endpoint
```
POST /ai/chat/text
```

**Request Body Change**:
- Old: `voice: "Fritz-PlayAI"`
- New: `voice: "vi-VN-Neural2-A"` (full Google TTS voice name)

**Backend Processing**:
- Extracts: `voice_name="vi-VN-Neural2-A"`, `language_code="vi-VN"`
- Calls: `text_to_speech_with_voice(text, path, voice_name, language_code)`

## Benefits

1. **More Voice Options**: 500+ voices across 40+ languages (vs. 19 PlayAI voices)
2. **Better Quality**: Google Neural2 and WaveNet voices with natural speech
3. **Hierarchical Selection**: Easy to navigate by language → model → voice
4. **Transparent**: Voice indicator shows exact configuration used
5. **Scalable**: Voice caching reduces API calls
6. **Flexible**: Easy to add new languages/models without code changes
7. **Native Integration**: Direct Google Cloud TTS API (no third-party intermediary)

## Notes

- Voice data is cached in memory (`_VOICES_CACHE`) after first API call
- Default language: Vietnamese (`vi-VN`)
- Default model: Neural2 (best quality for Vietnamese)
- Default voice: First available (typically `vi-VN-Neural2-A` for Vietnamese)
- Service account permissions required: `roles/cloudtexttospeech.admin`
- API key must be set in `GOOGLE_API_KEY` environment variable

## Rollback Plan

If issues occur, restore previous implementation:
1. Revert `template/utils/tts.py` to Groq PlayAI version
2. Revert `template/router/v1/ai.py` voice handling
3. Revert `static/*` files to single dropdown
4. Remove `/ai/voices` endpoint
5. Restart Docker container

## Support

For issues or questions:
- Check logs: `docker-compose logs -f`
- Test API: `curl http://localhost:9000/ai/voices`
- Debug UI: Open browser console, run `testVoiceSelection()`
- Verify service account: Check `service-account.json` has TTS permissions
