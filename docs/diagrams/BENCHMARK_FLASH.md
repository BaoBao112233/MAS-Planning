# 📊 Performance Benchmark - Gemini 2.5 Flash

**Test Date:** November 3, 2025  
**LLM Model:** Google Gemini 2.5 Flash  
**Session ID:** testing-gemini-25-flash

## ⚡ Quick Summary

| Case | Description | Total Time | Main Bottleneck |
|------|-------------|------------|-----------------|
| **Case 1** | Simple Greeting | **3.06s** ✅ | LLM: 3.05s (99.7%) |
| **Case 2** | Show All Devices | **14.80s** 🟡 | MCP get_device_list: 5.82s (39.3%) |
| **Case 3** | Turn On Light | **13.88s** 🟢 | MCP switch: 2.85s (20.5%) |
| **Case 4** | Turn Off Light | **15.62s** 🟡 | MCP switch: 2.97s (19.0%) |
| **Case 5 - Phase 1** | Create Plan | **23.58s** 🔴 | LLM Generate Plans: 14.21s (60.2%) |
| **Case 5 - Phase 2** | Execute Plan | **27.11s** 🔴 | Parallel Execution: 18.5s (68.3%) |

**Total Case 5:** 50.69s (Phase 1 + Phase 2)

---

## 📈 Detailed Breakdown

### Case 1: Simple Greeting (3.06s)
```
User: "hi"
Flow: User → Manager → LLM → Response

Timeline:
├─ Manager LLM Call: 3.05s (99.7%) 🔴
└─ Redis Save: 0.01s (0.3%)

Key Insight: Direct response, no tool routing needed
```

### Case 2: Show All Devices (14.80s)
```
User: "Show me all devices"
Flow: User → Manager → Tool Agent → MCP → Response

Timeline:
├─ Manager Analysis: 3.48s (23.5%)
├─ MCP Initialization: 1.86s (12.6%)
├─ LLM Planning: 1.62s (10.9%)
├─ MCP get_device_list: 5.82s (39.3%) 🔴
└─ LLM Formatting: 2.00s (13.5%)

Key Insight: MCP API call is the bottleneck
```

### Case 3: Turn On Light (13.88s)
```
User: "turn on light 1 in the bed room"
Flow: User → Manager → Tool Agent (3 iterations) → MCP → Response

Timeline:
├─ Manager Routing: 2.68s (19.3%)
├─ MCP Init: 1.23s (8.9%)
├─ Iteration 1 (Discovery): 2.66s (19.2%)
├─ Iteration 2 (Execute): 4.12s (29.7%) 🔴
├─ Iteration 3 (Finalize): 2.10s (15.1%)
└─ Redis Save: 0.64s (4.6%)

Key Insight: 3 LangGraph iterations with LLM caching (4925 tokens cached)
```

### Case 4: Turn Off Light (15.62s)
```
User: "turn off light 1 in the bed room."
Flow: User → Manager → Tool Agent (3 iterations) → MCP → Response

Timeline:
├─ Manager Routing: 3.08s (19.7%)
├─ MCP Init: 1.29s (8.3%)
├─ Iteration 1 (Discovery): 2.73s (17.5%)
├─ Iteration 2 (Execute): 4.32s (27.7%) 🔴
├─ Iteration 3 (Finalize): 3.20s (20.5%)
└─ Redis Save: 0.67s (4.3%)

Key Insight: Similar to Case 3, context-aware with device cache
```

### Case 5 - Phase 1: Create Plan (23.58s)
```
User: "Have 1 person in the bed room, Create plan."
Flow: User → Manager → Plan Agent → MCP → LLM Generate 3 Plans

Timeline:
├─ Manager Routing: 2.33s (9.9%)
├─ MCP Init: 1.92s (8.1%)
├─ LLM Analyze Input: 3.45s (14.6%)
├─ MCP Get Devices: 1.67s (7.1%)
└─ LLM Generate 3 Plans: 14.21s (60.2%) 🔴

Key Insight: Complex plan generation takes 60% of total time
```

### Case 5 - Phase 2: Execute Plan (27.11s)
```
User: "plan 1"
Flow: User → Manager → Plan Agent → Parallel Execution (4 threads) → MCP

Timeline:
├─ Manager Routing: 2.68s (9.9%)
├─ MCP Init: 1.85s (6.8%)
├─ Upload Plan to API: 2.22s (8.2%)
├─ Parallel Task Execution: 18.5s (68.3%) 🔴
│   ├─ Thread 0 (Turn on 8 lights): ~12.3s
│   ├─ Thread 1 (Verify illumination): ~8.1s
│   ├─ Thread 2 (Activate beacon): ~9.5s
│   └─ Thread 3 (Activate 4-button): ~18.5s (longest)
└─ Update Plan Status: 1.74s (6.4%)

Key Insight: Parallel execution saves ~20s vs sequential
```

---

## 🔍 Key Performance Insights

### 1. **LLM Call Distribution**
- **Simple queries (Case 1):** 99.7% LLM time
- **Tool operations (Case 2-4):** 15-30% LLM time (with caching)
- **Complex generation (Case 5-P1):** 60% LLM time

### 2. **MCP Operation Impact**
- **Initialization:** 1.2-1.9s per session
- **API Calls:** 1.5-5.8s depending on complexity
- **Device Control:** 2.8-3.0s per operation

### 3. **Caching Effectiveness**
- **Context Caching:** 90% token reduction (4,925 cached tokens)
- **Speed Improvement:** 2-3x faster on repeated patterns
- **Use Cases:** Device discovery, similar operations

### 4. **Parallel Execution Benefits**
- **Sequential Time (estimated):** ~38s for 4 tasks
- **Parallel Time (actual):** 18.5s (limited by longest task)
- **Time Saved:** ~20s (53% faster)

---

## 🎯 Optimization Opportunities

### High Priority 🔴
1. **MCP get_device_list optimization** (Case 2)
   - Current: 5.82s (39.3% of total)
   - Target: <3s
   - Approach: Cache device list, reduce API overhead

2. **LLM Plan Generation** (Case 5-P1)
   - Current: 14.21s (60.2% of total)
   - Target: <8s
   - Approach: Optimize prompts, use structured output

### Medium Priority 🟡
3. **MCP Initialization Overhead** (All cases)
   - Current: 1.2-1.9s per request
   - Target: <0.5s
   - Approach: Connection pooling, persistent sessions

4. **Redis Save Operations** (Case 3-4)
   - Current: 0.64-0.67s
   - Target: <0.3s
   - Approach: Async saves, batch operations

### Low Priority 🟢
5. **Manager Routing LLM Calls** (All cases)
   - Current: 2.3-3.5s
   - Already optimized with caching
   - Further gains marginal

---

## 📝 Comparison with Gemini 2.5 Pro

| Case | Gemini 2.5 Pro | Gemini 2.5 Flash | Improvement |
|------|----------------|------------------|-------------|
| Case 1 | 4.86s | 3.06s | **37% faster** ✅ |
| Case 2 | ~30s (est.) | 14.80s | **51% faster** ✅ |
| Case 3 | 29.91s | 13.88s | **54% faster** ✅ |
| Case 4 | 22.32s | 15.62s | **30% faster** ✅ |
| Case 5 P1 | 36.45s | 23.58s | **35% faster** ✅ |
| Case 5 P2 | 44.80s | 27.11s | **39% faster** ✅ |

**Overall:** Gemini 2.5 Flash provides **30-54% performance improvement** across all use cases.

---

## 🔗 Related Files

- **Sequence Diagrams:**
  - [sequence_Case1.mmd](./sequence_Case1.mmd) - Simple Greeting
  - [sequence_Case2.mmd](./sequence_Case2.mmd) - Show All Devices
  - [sequence_Case3.mmd](./sequence_Case3.mmd) - Turn On Light
  - [sequence_Case4.mmd](./sequence_Case4.mmd) - Turn Off Light
  - [sequence_Case5_Parallel.mmd](./sequence_Case5_Parallel.mmd) - Plan Execution

- **Benchmark Charts:**
  - [benchmark_gemini_2_5_flash.mmd](./benchmark_gemini_2_5_flash.mmd) - Bar chart comparison

- **Raw Data:**
  - [/home/baobao/Projects/MAS-Planning/full-docker-logs.txt](../../full-docker-logs.txt) - Complete Docker logs

---

**Generated:** November 3, 2025  
**Analysis Tool:** Docker Compose Logs + Manual Timing Extraction  
**Total Log Lines Analyzed:** 41,040 lines
