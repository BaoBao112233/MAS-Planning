# Quick Fix: Plan Agent Optimization
## Giảm thời gian từ 30s → 12-15s

### 🔍 Phân tích từ logs

```
Timing breakdown (30.46s total):
├─ Manager routing:     7.0s  (23%)  ← Pattern routing saves 6.9s
├─ Plan Agent init:     3.0s  (10%)  ← MCP connection overhead
├─ Step 1 (Analyze):    7.0s  (23%)  ← LLM call - CAN MERGE
├─ Step 2 (Get devices):2.0s  (7%)   ← MCP tool - CAN CACHE
├─ Step 3 (Create plans):12.0s (39%) ← LLM call - USE FLASH
└─ Other:               2.5s  (8%)
```

### 🎯 Quick Wins (Implement trong 30 phút)

#### 1. Switch to Gemini Flash (Save ~15s)

**File**: `template/agent/plan/__init__.py`

**Change line 38-39**:
```python
# BEFORE:
class PlanAgent(BaseAgent):
    def __init__(self, 
                 model: str = "gemini-2.5-pro",  # ← Slow!
                 temperature: float = 0.2,
```

**TO**:
```python
# AFTER:
class PlanAgent(BaseAgent):
    def __init__(self, 
                 model: str = "gemini-2.5-flash",  # ← Fast!
                 temperature: float = 0.2,
```

**Expected savings**: 
- Analyze input: 7s → 2s (5s saved)
- Create plans: 12s → 4s (8s saved)
- **Total: 13s saved**

---

#### 2. Enable Pattern Routing for Manager (Save ~7s)

**File**: `template/agent/manager/__init__.py`

**Add at top**:
```python
from optimizations.pattern_routing import PatternRouter
```

**Add in __init__**:
```python
class ManagerAgent:
    def __init__(self):
        # ... existing code ...
        
        # Add pattern router
        self.pattern_router = PatternRouter()
```

**Modify analyze_query method** (around line 150):
```python
async def analyze_query(self, user_query: str, chat_history: list):
    """Enhanced with pattern routing"""
    
    # Try pattern routing first
    pattern_result = self.pattern_router.route(user_query)
    
    if pattern_result['confidence'] > 0.8:
        logger.info(
            f"⚡ Fast pattern routing: {pattern_result['agent']} "
            f"(confidence: {pattern_result['confidence']:.2f})"
        )
        return {
            "agent": pattern_result['agent'],
            "reasoning": f"Pattern matched: {pattern_result['pattern']}",
            "confidence": pattern_result['confidence'],
        }
    
    # Low confidence - fallback to LLM
    logger.info("🤔 Using LLM routing (pattern confidence too low)")
    
    # ... rest of existing analyze_query code ...
```

**Expected savings**: Manager routing: 7s → 0.1s (6.9s saved)

---

#### 3. Cache Device List (Save ~2s)

**File**: `template/agent/plan/__init__.py`

**Add at top**:
```python
from optimizations.device_caching import SmartDeviceCache
```

**Add in __init__**:
```python
class PlanAgent(BaseAgent):
    def __init__(self, ...):
        # ... existing code ...
        
        # Add device cache
        self.device_cache = SmartDeviceCache(ttl_seconds=600)  # 10 min TTL
```

**Modify get_device_info method** (around line 300):
```python
async def get_device_info(self, state: PlanState) -> PlanState:
    """Enhanced with caching"""
    logger.info("=" * 80)
    logger.info("🎯 STEP 2: RETRIEVING DEVICE INFORMATION")
    logger.info("=" * 80)
    
    token = state.get("token", "")
    
    # Try cache first
    cached_devices = await self.device_cache.get_cached_devices(token)
    
    if cached_devices:
        logger.info("✅ Using cached device list")
        logger.info(f"📱 Device data retrieved: {len(str(cached_devices))} characters")
        return {
            **state,
            "device_context": cached_devices,
        }
    
    # Cache miss - fetch from MCP
    logger.info("📡 Calling get_device_list tool...")
    
    # ... existing get_device_list code ...
    # After getting result:
    
    # Update cache
    await self.device_cache.update_devices(token, device_data)
    logger.info("💾 Cached device list for future requests")
    
    return {
        **state,
        "device_context": device_data,
    }
```

**Expected savings**: Get device list: 2s → 0s (2s saved on cache hit)

---

### 📊 Expected Results

**BEFORE**:
```
Total: 30.46s
├─ Manager routing:    7.0s
├─ Plan init:          3.0s
├─ Analyze input:      7.0s
├─ Get devices:        2.0s
├─ Create plans:      12.0s
└─ Other:              2.5s
```

**AFTER (Quick Wins)**:
```
Total: ~12-15s ✅
├─ Manager routing:    0.1s  (pattern routing)
├─ Plan init:          2.0s  (flash model faster)
├─ Analyze input:      2.0s  (flash model)
├─ Get devices:        0.0s  (cached)
├─ Create plans:       4.0s  (flash model)
└─ Other:              2.5s
```

**Total savings**: ~18s (60% faster!)

---

### 🧪 Testing

1. **Build and restart**:
```bash
sudo docker compose down
sudo docker compose up --build -d
```

2. **Test plan creation**:
```bash
# Watch logs
sudo docker compose logs -f

# Send test request (in another terminal)
curl -X POST http://localhost:9000/ai/chat/text \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "test123",
    "message": "Have 1 person in living room. Temperature 20C. Create plan.",
    "token": "test-token-123"
  }'
```

3. **Check timing in logs**:
Look for: `✅ Request processed successfully in X.XXs`

**Expected**: ~12-15s (down from 30.46s)

---

### 🔄 Rollback (if needed)

If Flash model quality is not good enough:

**File**: `template/agent/plan/__init__.py`

Change back to:
```python
model: str = "gemini-2.5-pro",
```

Restart:
```bash
sudo docker compose restart
```

---

### 🚀 Advanced Optimization (Optional - Implement later)

**Combine Step 1 & Step 3** (Save additional 7s):

Instead of:
1. Analyze input (7s LLM call)
2. Create plans (12s LLM call)

Do:
1. Create plans directly (single 8-10s LLM call)

**Implementation**: Use `optimizations/plan_agent_optimization.py` → `get_combined_prompt()`

This merges the two prompts into one, eliminating one LLM round-trip.

---

### ✅ Summary

**Quick Wins** (30 minutes implementation):
- ✅ Switch to Flash model (13s saved)
- ✅ Pattern routing (7s saved)  
- ✅ Device caching (2s saved)

**Total**: 30.46s → **12-15s** (60% improvement)

**Advanced** (later):
- Combine prompts (7s additional savings)
- Target: **8-10s**
