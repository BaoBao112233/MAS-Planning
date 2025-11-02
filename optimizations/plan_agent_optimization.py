"""
Plan Agent Optimization
Giảm thời gian từ 30s → 12-15s
"""
import logging

logger = logging.getLogger(__name__)


class PlanAgentOptimizer:
    """
    Optimization strategies for Plan Agent
    
    Current bottlenecks:
    - Manager routing: 7s
    - Step 1 (Analyze input): 7s  
    - Step 2 (Get device list): 2s
    - Step 3 (Create plans): 12s
    Total: 30.46s
    
    Target: 12-15s
    """
    
    @staticmethod
    def get_optimized_model_config():
        """
        Optimization 1: Use Gemini Flash for Plan Agent
        
        Savings: ~15-18s (all LLM calls faster)
        - Analyze input: 7s → 2s (5s saved)
        - Create plans: 12s → 3-4s (8-9s saved)
        - Manager routing: 7s → 2s (if pattern routing not applied)
        
        Trade-off: Slightly lower quality but still good for planning
        """
        return {
            'model_name': 'gemini-2.5-flash',
            'temperature': 0.2,
            'max_tokens': 1024,  # Limit for faster response
            'top_p': 0.9,
        }
    
    @staticmethod
    def get_combined_prompt(user_input: str, device_context: str) -> str:
        """
        Optimization 2: Combine Step 1 & Step 3 into ONE LLM call
        
        Savings: ~7s (eliminate one LLM call)
        - Current: Analyze (7s) + Create plans (12s) = 19s
        - Optimized: Single call (8-10s) = 8-10s
        - Savings: 9-11s
        
        Trade-off: More complex prompt but faster overall
        """
        return f"""
🎯 **ROLE**: You are a smart home automation planner. Create 3 priority-based plans in ONE STEP.

## 📝 USER REQUEST
{user_input}

## 🏠 AVAILABLE DEVICES
{device_context}

## 🎨 YOUR TASK
Analyze the request and immediately create 3 plans with different priorities:

### **Plan 1: Security Priority** 🔒
Focus on safety, protection, monitoring.
- Lock doors, enable cameras, turn on security lights
- 3-5 specific tasks using actual device names

### **Plan 2: Convenience Priority** 🏠  
Focus on user comfort and ease of use.
- Comfortable temperature, pleasant lighting, automation
- 3-5 specific tasks using actual device names

### **Plan 3: Energy Efficiency Priority** 🌱
Focus on minimizing energy consumption.
- Turn off unused devices, optimize settings, eco mode
- 3-5 specific tasks using actual device names

## 📤 RESPONSE FORMAT (MANDATORY)

<Security_Plan>
- Task 1 (specific, using actual device name)
- Task 2 (specific, using actual device name)
- Task 3 (specific, using actual device name)
</Security_Plan>

<Convenience_Plan>
- Task 1 (specific, using actual device name)
- Task 2 (specific, using actual device name)
- Task 3 (specific, using actual device name)
</Convenience_Plan>

<Energy_Plan>
- Task 1 (specific, using actual device name)
- Task 2 (specific, using actual device name)
- Task 3 (specific, using actual device name)
</Energy_Plan>

**RULES**:
1. Use actual device names from the device list
2. Write in natural language (not API calls)
3. Be specific (include room names, settings, values)
4. Make each task independently executable
5. Each plan should have 3-5 tasks

Create the 3 plans now!
"""
    
    @staticmethod
    def cache_device_list(token: str, devices: dict, ttl_seconds: int = 600):
        """
        Optimization 3: Cache device list for 10 minutes
        
        Savings: ~2s per request (skip get_device_list call)
        
        For Plan Agent, device list changes are rare, so longer TTL is OK
        """
        from optimizations.device_caching import SmartDeviceCache
        
        cache = SmartDeviceCache(ttl_seconds=ttl_seconds)
        return cache


# ============================================================
# Integration Example
# ============================================================

async def optimized_plan_agent_workflow(self, state: dict):
    """
    Optimized Plan Agent workflow
    
    BEFORE (30.46s):
    1. Manager routing (7s)
    2. Analyze input (7s)  
    3. Get device list (2s)
    4. Create plans (12s)
    5. Format response (2.46s)
    
    AFTER (12-15s):
    1. Manager routing (0.1s) ← Pattern routing
    2. Get device list (0s) ← Cached  
    3. Create plans (8-10s) ← Flash model + Combined prompt
    4. Format response (2s)
    
    Total savings: 15-18s
    """
    from template.agent.plan.utils import extract_priority_plans
    from template.message.message import HumanMessage
    from langchain_google_vertexai import ChatVertexAI
    from template.configs.environments import env
    
    user_input = state.get("user_input", "")
    token = state.get("token", "")
    
    logger.info("=" * 80)
    logger.info("🚀 OPTIMIZED PLAN AGENT WORKFLOW")
    logger.info("=" * 80)
    
    # Step 1: Get device list (use cache if available)
    optimizer = PlanAgentOptimizer()
    device_cache = optimizer.cache_device_list(token, {})
    
    cached_devices = await device_cache.get_cached_devices(token)
    
    if cached_devices:
        logger.info("✅ Using cached device list")
        device_context = cached_devices
        step2_time = 0
    else:
        logger.info("📡 Fetching device list...")
        import time
        start = time.time()
        
        # Call get_device_list tool
        from mcp.client.sse import sse_client
        async with sse_client(f"http://localhost:8000/sse/device") as streams:
            client, session = streams
            result = await self.api_client.execute_mcp_tool(
                client=client,
                session=session,
                tool_name="get_device_list",
                arguments={}
            )
        
        device_context = result
        await device_cache.update_devices(token, device_context)
        step2_time = time.time() - start
        logger.info(f"✅ Device list fetched in {step2_time:.2f}s")
    
    # Step 2: Create plans with optimized LLM (Combined prompt)
    logger.info("🤖 Creating 3 priority plans with optimized LLM...")
    
    # Use Flash model
    model_config = optimizer.get_optimized_model_config()
    llm = ChatVertexAI(
        **model_config,
        project=env.GOOGLE_CLOUD_PROJECT,
        location=env.GOOGLE_CLOUD_LOCATION,
    )
    
    # Combined prompt (skip analyze step)
    combined_prompt = optimizer.get_combined_prompt(
        user_input=user_input,
        device_context=str(device_context)
    )
    
    import time
    start = time.time()
    
    response = await llm.ainvoke([HumanMessage(content=combined_prompt)])
    
    llm_time = time.time() - start
    logger.info(f"✅ Plans created in {llm_time:.2f}s")
    
    # Step 3: Extract plans
    plans = extract_priority_plans(response.content)
    
    logger.info(f"✅ Extracted {len(plans)} plans")
    logger.info("=" * 80)
    
    return {
        **state,
        "plans": plans,
        "selected_plan": None,
        "timing": {
            "device_list": step2_time,
            "create_plans": llm_time,
            "total": step2_time + llm_time,
        }
    }


# ============================================================
# Drop-in Replacement
# ============================================================

"""
INTEGRATION STEPS:

1. Modify template/agent/plan/__init__.py:

```python
from optimizations.plan_agent_optimization import PlanAgentOptimizer

class PlanAgent(BaseAgent):
    def __init__(self, model: str = "gemini-2.5-flash", ...):  # ← Change to flash
        # ... existing code ...
        
        # Add optimizer
        self.optimizer = PlanAgentOptimizer()
        
        # Use optimized model config
        config = self.optimizer.get_optimized_model_config()
        self.llm = ChatVertexAI(
            **config,
            project=env.GOOGLE_CLOUD_PROJECT,
            location=env.GOOGLE_CLOUD_LOCATION,
        )
```

2. Replace workflow method:

```python
# In create_graph():
def create_graph(self):
    workflow = StateGraph(PlanState)
    
    # Add optimized workflow
    workflow.add_node("create_plans", self.optimized_create_plans)
    
    # ... rest of graph ...
    
    return workflow.compile()

async def optimized_create_plans(self, state: dict):
    '''Use combined prompt instead of 2 separate LLM calls'''
    from optimizations.plan_agent_optimization import optimized_plan_agent_workflow
    return await optimized_plan_agent_workflow(self, state)
```

3. Enable pattern routing for Manager Agent:

```python
# In template/agent/manager/__init__.py
from optimizations.pattern_routing import PatternRouter

class ManagerAgent:
    def __init__(self):
        self.pattern_router = PatternRouter()
    
    async def analyze_query(self, query: str, history: list):
        # Try pattern first
        result = self.pattern_router.route(query)
        
        if result['confidence'] > 0.8:
            return {
                'agent': result['agent'],
                'reasoning': f"Pattern: {result['pattern']}",
                'confidence': result['confidence'],
            }
        
        # Fallback to LLM
        return await self.llm_analyze(query, history)
```
"""


# ============================================================
# Expected Results
# ============================================================

"""
BEFORE:
-------
17:23:53 - Request starts
17:24:00 - Manager routing complete (7s)
17:24:03 - Plan Agent init (3s)  
17:24:10 - Analyze input complete (7s)
17:24:12 - Get device list complete (2s)
17:24:24 - Create plans complete (12s)
17:24:24 - Total: 30.46s ❌

AFTER (with optimizations):
--------------------------
00:00:00 - Request starts
00:00:00 - Manager routing complete (0.1s) ← Pattern routing
00:00:02 - Plan Agent init (2s) ← Faster with flash
00:00:02 - Get device list complete (0s) ← Cached
00:00:10 - Create plans complete (8s) ← Flash + Combined prompt
00:00:12 - Total: ~12s ✅

SAVINGS: 18.46s (60% faster!)

Breakdown:
- Manager routing: 7s → 0.1s (6.9s saved)
- Plan Agent init: 3s → 2s (1s saved)
- Analyze input: 7s → 0s (7s saved, merged into create plans)
- Get device list: 2s → 0s (2s saved, cached)
- Create plans: 12s → 8s (4s saved, flash model)
"""
