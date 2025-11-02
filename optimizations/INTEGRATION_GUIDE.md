# Integration Guide
## Hướng dẫn tích hợp các optimizations vào hệ thống

Các file optimization đã tạo:
1. `pattern_routing.py` - Fast routing cho Manager Agent
2. `device_caching.py` - Cache device list
3. `model_selection.py` - Smart model selection (Flash vs Pro)
4. `connection_pooling.py` - Reuse MCP connections
5. `oneshot_prompting.py` - Tối ưu prompts để giảm iterations

---

## Phase 1: Quick Wins (Target: 29.91s → 12-15s)

### 1.1 Pattern Routing (8.4s savings)

**File to modify**: `template/agent/manager/__init__.py`

```python
from optimizations.pattern_routing import PatternRouter

class ManagerAgent:
    def __init__(self):
        # ... existing code ...
        
        # Add pattern router
        self.pattern_router = PatternRouter()
    
    async def analyze_query(self, user_query: str, chat_history: list):
        # Try pattern matching first
        pattern_result = self.pattern_router.route(user_query)
        
        if pattern_result['confidence'] > 0.8:
            # High confidence - use pattern result
            logger.info(
                f"⚡ Fast pattern routing: {pattern_result['agent']} "
                f"(confidence: {pattern_result['confidence']:.2f})"
            )
            return {
                "agent": pattern_result['agent'],
                "reasoning": f"Pattern matched: {pattern_result['pattern']}",
                "confidence": pattern_result['confidence'],
            }
        
        # Low confidence - fallback to LLM routing
        logger.info("🤔 Using LLM routing (pattern confidence too low)")
        return await self.llm_analyze_query(user_query, chat_history)
    
    async def llm_analyze_query(self, user_query: str, chat_history: list):
        # ... existing LLM routing code ...
        pass
```

**Environment variable**:
```bash
# docker-compose.yml
environment:
  - PATTERN_ROUTING_ENABLED=true
  - PATTERN_MIN_CONFIDENCE=0.8
```

**Testing**:
```bash
# Test pattern routing
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Turn on Light 1 in bedroom"}'

# Should see in logs:
# ⚡ Fast pattern routing: tool (confidence: 0.95)
```

**Expected result**: Manager routing time: 8.498s → 0.1s

---

### 1.2 Device Caching (6.3s savings)

**File to modify**: `template/agent/tool/__init__.py`

```python
from optimizations.device_caching import SmartDeviceCache

class ToolAgent:
    def __init__(self):
        # ... existing code ...
        
        # Add device cache
        self.device_cache = SmartDeviceCache(
            ttl_seconds=300,  # 5 minutes
            verbose=True
        )
    
    async def reason_and_plan(self, state: dict):
        """Enhanced with device caching"""
        token = state.get("token", "")
        
        # Try to inject cached devices
        cached = await self.device_cache.get_cached_devices(token)
        
        if cached:
            # Inject cache into context
            cache_msg = f"""
CACHED DEVICE LIST (use these directly):
{json.dumps(cached, indent=2, ensure_ascii=False)}

IMPORTANT:
- This device list is fresh and complete
- Use device IDs directly for control
- DO NOT call get_device_list again
"""
            
            # Insert before first message
            if 'messages' not in state:
                state['messages'] = []
            
            from template.message.message import HumanMessage
            state['messages'].insert(0, HumanMessage(content=cache_msg))
            
            logger.info("📋 Injected cached device list")
        
        # Continue with normal reasoning
        return await self._original_reason_and_plan(state)
    
    async def execute_tools_parallel(self, tools_to_execute: list, state: dict):
        """Enhanced to update cache"""
        # Execute tools
        results = await self._original_execute_tools_parallel(tools_to_execute)
        
        # Update cache if get_device_list was called
        for tool, result in zip(tools_to_execute, results):
            if tool.get("name") == "get_device_list" and result.get("status") == "success":
                token = state.get("token", "")
                device_data = result.get("result", [])
                
                await self.device_cache.update_devices(token, device_data)
                logger.info(f"💾 Updated device cache for user")
        
        return results
```

**Testing**:
```bash
# First request (cache miss)
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "Turn on Light 1"}'
# Should see: get_device_list called, then turn_on_device

# Second request (cache hit)
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "Turn off Light 2"}'
# Should see: turn_off_device ONLY (skipped get_device_list)
```

**Expected result**: Tool iterations reduced from 3 to 2

---

### 1.3 Gemini Flash Model (13s savings)

**File to modify**: `template/agent/tool/__init__.py`, `template/agent/manager/__init__.py`

```python
from optimizations.model_selection import ModelSelector

class ToolAgent:
    async def init_async(self, user_query: str = ""):
        # Smart model selection
        llm_config = ModelSelector.get_llm_config(
            query=user_query,
            force_model='flash'  # Always use flash for Tool Agent
        )
        
        from langchain_google_vertexai import ChatVertexAI
        self.base_llm = ChatVertexAI(
            **llm_config,
            project=env.GOOGLE_CLOUD_PROJECT,
            location=env.GOOGLE_CLOUD_LOCATION,
        )

class ManagerAgent:
    def __init__(self, user_query: str = ""):
        # Smart model selection for Manager
        llm_config = ModelSelector.get_llm_config(query=user_query)
        
        from langchain_google_vertexai import ChatVertexAI
        self.llm = ChatVertexAI(
            **llm_config,
            project=env.GOOGLE_CLOUD_PROJECT,
            location=env.GOOGLE_CLOUD_LOCATION,
        )
```

**Environment variables**:
```bash
# docker-compose.yml
environment:
  - FORCE_MODEL=flash  # Global override
  - TOOL_AGENT_FORCE_FLASH=true
```

**Testing**:
```bash
# Check model being used
grep "model_name" logs/docker-logs.txt

# Should see: gemini-2.5-flash (not gemini-2.5-pro)
```

**Expected result**: LLM response time: ~6-8s → ~2-3s per call

---

## Phase 2: Advanced Optimizations (Target: 15s → 8-10s)

### 2.1 MCP Connection Pooling (1-2s savings)

**File to modify**: `template/agent/tool/__init__.py`

```python
from optimizations.connection_pooling import get_pool

class ToolAgent:
    async def execute_tools_parallel(self, tools_to_execute: list):
        pool = get_pool()
        
        async def execute_single_tool(tool):
            try:
                server_name = tool["server_name"]
                tool_name = tool["name"]
                arguments = tool["arguments"]
                
                # Use connection pool
                client, session = await pool.get_connection(server_name)
                
                # Execute tool
                from template.agent.api_client import get_api_client
                api_client = get_api_client()
                
                result = await api_client.execute_mcp_tool(
                    client=client,
                    session=session,
                    tool_name=tool_name,
                    arguments=arguments,
                )
                
                return {
                    "tool": tool_name,
                    "result": result,
                    "status": "success",
                }
            except Exception as e:
                logger.error(f"Error: {e}")
                return {"error": str(e), "status": "error"}
        
        # Execute in parallel
        tasks = [execute_single_tool(t) for t in tools_to_execute]
        return await asyncio.gather(*tasks)
```

**Cleanup on shutdown** (`main.py`):
```python
from optimizations.connection_pooling import cleanup_pool
import atexit

# Register cleanup
atexit.register(lambda: asyncio.run(cleanup_pool()))
```

---

### 2.2 One-Shot Prompting (7-11s savings)

**File to modify**: `template/agent/tool/prompt.py`

```python
from optimizations.oneshot_prompting import OneShotPrompts

# Replace SYSTEM_PROMPT with:
SYSTEM_PROMPT = OneShotPrompts.TOOL_AGENT_SYSTEM
```

**File to modify**: `template/agent/tool/__init__.py`

```python
from optimizations.oneshot_prompting import OneShotPrompts

class ToolAgent:
    async def reason_and_plan(self, state: dict):
        # Create one-shot prompt
        prompt = OneShotPrompts.create_tool_agent_prompt(
            user_query=state.get("user_query", ""),
            chat_history=state.get("messages", []),
            available_tools=state.get("available_tools", []),
        )
        
        # Single LLM call
        from template.message.message import HumanMessage
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        
        # Parse response
        import re
        content = response.content
        
        reasoning_match = re.search(r'Reasoning:\s*(.+?)(?=Tools:|Response:|$)', content, re.DOTALL)
        tools_match = re.search(r'Tools:\s*(.+?)(?=Response:|$)', content, re.DOTALL)
        response_match = re.search(r'Response:\s*(.+?)$', content, re.DOTALL)
        
        reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
        tools_text = tools_match.group(1).strip() if tools_match else "[]"
        final_response = response_match.group(1).strip() if response_match else ""
        
        # Parse tools
        tools_to_execute = self._parse_tools(tools_text) if tools_text != "[]" else []
        
        return {
            **state,
            "reasoning": reasoning,
            "tools_to_execute": tools_to_execute,
            "final_response": final_response,
            "iterations": 1,  # ONE SHOT!
        }
```

---

## Testing Strategy

### Automated Tests

```python
# tests/test_optimizations.py
import pytest
import asyncio
from optimizations.pattern_routing import PatternRouter
from optimizations.device_caching import SmartDeviceCache
from optimizations.model_selection import ModelSelector

@pytest.mark.asyncio
async def test_pattern_routing():
    router = PatternRouter()
    
    # Test device control pattern
    result = router.route("Turn on Light 1")
    assert result['agent'] == 'tool'
    assert result['confidence'] > 0.8
    
    # Test plan pattern
    result = router.route("Create morning routine")
    assert result['agent'] == 'plan'
    assert result['confidence'] > 0.8

@pytest.mark.asyncio
async def test_device_caching():
    cache = SmartDeviceCache()
    
    # Simulate cache update
    devices = [
        {"id": "device_light_1", "name": "Light 1"},
        {"id": "device_light_2", "name": "Light 2"},
    ]
    
    await cache.update_devices("test_token", devices)
    
    # Verify cache hit
    cached = await cache.get_cached_devices("test_token")
    assert cached is not None
    assert len(cached) == 2

def test_model_selection():
    # Simple query → flash
    config = ModelSelector.get_llm_config("Turn on light")
    assert config['model_name'] == 'gemini-2.5-flash'
    
    # Complex query → pro
    config = ModelSelector.get_llm_config("Create automation")
    assert config['model_name'] == 'gemini-2.5-pro'
```

Run tests:
```bash
pytest tests/test_optimizations.py -v
```

---

### Manual End-to-End Tests

```bash
# Test Case 1: Simple device control
time curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "Turn on Light 1 in bedroom"}'

# Expected: < 10s (was 29.91s)

# Test Case 2: Multiple devices
time curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "Turn off all lights"}'

# Expected: < 15s (was 22.32s)

# Test Case 3: Info query
time curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "What is the weather?"}'

# Expected: < 8s
```

---

### A/B Testing

```python
# template/configs/environments.py
import os

class OptimizationConfig:
    # Feature flags
    PATTERN_ROUTING_ENABLED = os.getenv('PATTERN_ROUTING_ENABLED', 'true') == 'true'
    DEVICE_CACHING_ENABLED = os.getenv('DEVICE_CACHING_ENABLED', 'true') == 'true'
    USE_FLASH_MODEL = os.getenv('USE_FLASH_MODEL', 'true') == 'true'
    CONNECTION_POOLING_ENABLED = os.getenv('CONNECTION_POOLING_ENABLED', 'true') == 'true'
    ONESHOT_PROMPTING_ENABLED = os.getenv('ONESHOT_PROMPTING_ENABLED', 'false') == 'true'
    
    # Thresholds
    PATTERN_MIN_CONFIDENCE = float(os.getenv('PATTERN_MIN_CONFIDENCE', '0.8'))
    CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_SECONDS', '300'))
```

Docker Compose for A/B testing:
```yaml
# docker-compose.yml
services:
  # Control group (no optimizations)
  app-control:
    build: .
    environment:
      - PATTERN_ROUTING_ENABLED=false
      - DEVICE_CACHING_ENABLED=false
      - USE_FLASH_MODEL=false
    ports:
      - "8000:8000"
  
  # Treatment group (all optimizations)
  app-optimized:
    build: .
    environment:
      - PATTERN_ROUTING_ENABLED=true
      - DEVICE_CACHING_ENABLED=true
      - USE_FLASH_MODEL=true
      - CONNECTION_POOLING_ENABLED=true
      - ONESHOT_PROMPTING_ENABLED=true
    ports:
      - "8001:8000"
```

---

## Monitoring

### Add metrics tracking

```python
# template/agent/tool/__init__.py
import time

class ToolAgent:
    async def execute(self, state: dict):
        start_time = time.time()
        
        # ... execution code ...
        
        # Log metrics
        duration = time.time() - start_time
        logger.info(f"""
📊 Execution Metrics:
   Duration: {duration:.2f}s
   Iterations: {state.get('iterations', 0)}
   Tools called: {len(state.get('tools_to_execute', []))}
   Cache hits: {self.device_cache.get_stats()['hits'] if hasattr(self, 'device_cache') else 0}
""")
```

### Prometheus metrics (optional)

```python
from prometheus_client import Counter, Histogram

# Metrics
request_duration = Histogram('request_duration_seconds', 'Request duration')
cache_hits = Counter('cache_hits_total', 'Cache hits')
cache_misses = Counter('cache_misses_total', 'Cache misses')

# Track
with request_duration.time():
    result = await agent.execute(state)

if cache_hit:
    cache_hits.inc()
else:
    cache_misses.inc()
```

---

## Rollback Plan

If optimizations cause issues:

```bash
# Disable all optimizations
docker-compose down
docker-compose up -d \
  -e PATTERN_ROUTING_ENABLED=false \
  -e DEVICE_CACHING_ENABLED=false \
  -e USE_FLASH_MODEL=false \
  -e CONNECTION_POOLING_ENABLED=false \
  -e ONESHOT_PROMPTING_ENABLED=false
```

Or disable individually:
```bash
# Disable only pattern routing
export PATTERN_ROUTING_ENABLED=false
docker-compose restart
```

---

## Summary

**Phase 1 (Quick Wins - 1-2 days):**
- ✅ Pattern routing (8.4s savings)
- ✅ Device caching (6.3s savings)
- ✅ Gemini Flash (13s savings)
- **Expected: 29.91s → 12-15s**

**Phase 2 (Advanced - 3-5 days):**
- ✅ Connection pooling (1-2s savings)
- ✅ One-shot prompting (7-11s savings)
- **Expected: 15s → 8-10s**

**Target achieved: 8-10s (from 29.91s) = 66-73% reduction** ✅
