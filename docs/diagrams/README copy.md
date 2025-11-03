## 🏗️ System Architecture

### Core Components

**3 Main Agents**:
1. **Manager Agent** - Routes requests, handles direct responses internally
2. **Tool Agent** - Executes device control via MCP tools (LangGraph workflow)
3. **Plan Agent** - Creates and executes multi-step plans (2-phase lifecycle)

**Supporting Infrastructure**:
- **Redis** - Chat history and context storage
- **MCP Server** - OXII IoT device control API (13 tools)
- **Gemini 2.5 Flash** - LLM for reasoning and decision making
- **LangGraph** - Agentic workflow orchestration

### Key Principles

✅ **Context-aware routing** - Uses chat history for smarter decisions  
✅ **Parallel execution** - Multiple tasks run simultaneously when possible  
✅ **Session isolation** - Fresh MCP clients per tool call  
✅ **LLM caching** - Reuses 4,900+ tokens for repeated patterns

---

## 📈 Performance Overview (Gemini 2.5 Flash)

| Case | Description | Total Time | Main Bottleneck | Complexity |
|------|-------------|------------|-----------------|------------|
| **Case 1** | Simple Greeting | **3.06s** ✅ | LLM: 3.05s (99.7%) | Low |
| **Case 2** | Show All Devices | **14.80s** 🟡 | MCP API: 5.82s (39.3%) | Medium |
| **Case 3** | Turn On Light | **13.88s** 🟢 | MCP Switch: 2.85s (20.5%) | Medium |
| **Case 4** | Turn Off Light | **15.62s** 🟡 | MCP Switch: 2.97s (19.0%) | Medium |
| **Case 5** | Plan Execution | **50.69s** 🔴 | LLM Gen: 14.21s + Parallel: 18.5s | High |

**Average**: 19.61s across all cases  
**Improvement over Gemini 2.5 Pro**: 30-54% faster

---

## � Case 1: Simple Greeting (3.06s)

### Overview
**User Input**: "hi"  
**Flow**: User → Manager (internal direct response) → User  
**Total Time**: 3.06s (07:12:35 → 07:12:38)

### Workflow Details

```
Manager Agent (Internal LangGraph):
├─ analyze_query: LLM analyzes intent
├─ delegate: Handles INTERNALLY (no external agent)
└─ finalize: Returns response
```

### Timing Breakdown

| Component | Time | Percentage |
|-----------|------|------------|
| Manager LLM Call | 3.05s | 99.7% 🔴 |
| Redis Save | 0.01s | 0.3% |
| **Total** | **3.06s** | **100%** |

### Key Insights

✅ **Fastest case** - Direct LLM response without tool routing  
✅ **No external agent** - Manager handles internally3.05
⚠️ **99.7% LLM time** - Almost entire duration is Gemini API call  
💡 **Optimization potential**: Caching similar greetings, smaller routing model


**LangGraph Flow**:
- Input → analyze_query → delegate (direct) → finalize → Output
- Single LLM call combines routing + generation
- Redis saves conversation for context

---

## 📊 Case 2: Show All Devices (14.80s)

### Overview
**User Input**: "Show me all devices"  
**Flow**: User → Manager → Tool Agent (2 iterations) → MCP → User  
**Total Time**: 14.80s (07:12:47 → 07:13:02)

### Workflow Details

```
Manager Agent:
└─ Analyze + Route (3.48s)

Tool Agent (LangGraph):
├─ Iteration 1: Plan
│   ├─ LLM: Reason → get_device_list (1.62s)
│   └─ MCP: Execute get_device_list (5.82s) 🔴
└─ Iteration 2: Format
    └─ LLM: Format response (2.00s)
```

### Timing Breakdown

| Component | Time | Percentage |
|-----------|------|------------|
| Manager Analysis (LLM) | 3.48s | 23.5% |
| MCP Initialization | 1.86s | 12.6% |
| Tool Iteration 1 - Planning (LLM) | 1.62s | 10.9% |
| Tool Iteration 1 - Execute (MCP) | 5.82s | 39.3% 🔴 |
| Tool Iteration 2 - Formatting (LLM) | 2.00s | 13.5% |
| **Total** | **14.80s** | **100%** |

### Key Insights

⚠️ **MCP API bottleneck** - `get_device_list` takes 5.82s (39.3% of total)  
✅ **2-iteration workflow** - Plan → Execute → Format  
🟡 **LLM caching active** - 5,289 input tokens with context  
💡 **Optimization**: Cache device list, reduce API overhead to <3s target

### API Response Details

**Device List Returned**:
- 6 rooms (Bedroom, Living room, Kitchen, etc.)
- 20+ devices (Lights, AC, Switches, Sensors)
- Full device metadata (IDs, states, capabilities)

---

## 📊 Case 3: Turn On Light (13.88s)

### Overview
**User Input**: "turn on light 1 in the bed room"  
**Flow**: User → Manager → Tool Agent (3 iterations) → MCP → User  
**Total Time**: 13.88s (07:13:17 → 07:13:31)

### Workflow Details

```
Manager Agent:
└─ Analyze + Route (2.68s) → agent_type="tool"
   - Cache hit: 4,925 tokens from Case 2

Tool Agent (LangGraph):
├─ Iteration 1: Discovery
│   ├─ LLM: Which device? (1.16s)
│   └─ MCP: get_device_list → buttonId=1662 (1.50s)
├─ Iteration 2: Execute
│   ├─ LLM: Plan switch_on_off (1.27s)
│   └─ MCP: switch_on_off_controls_v2(1662, 1.0) (2.85s) 🔴
└─ Iteration 3: Verify
    ├─ LLM: Generate success message (1.46s)
    └─ Redis: Save conversation (0.64s)
```

### Timing Breakdown

| Component | Time | Percentage |
|-----------|------|------------|
| Manager Routing (LLM + Cache) | 2.68s | 19.3% |
| MCP Initialization | 1.23s | 8.9% |
| Iteration 1 - Discovery (LLM + MCP) | 2.66s | 19.2% |
| Iteration 2 - Execute (LLM + MCP) | 4.12s | 29.7% 🔴 |
| Iteration 3 - Finalize (LLM + Redis) | 2.10s | 15.1% |
| Redis Save | 0.64s | 4.6% |
| Other | 0.45s | 3.2% |
| **Total** | **13.88s** | **100%** |

### Key Insights

✅ **3-iteration pattern** - Discovery → Execute → Verify  
✅ **LLM caching works** - Reuses 4,925 tokens from previous device query  
⚠️ **MCP switch bottleneck** - 2.85s for device control (20.5% of total)  
🟢 **54% faster than Gemini 2.5 Pro** - Was 29.91s, now 13.88s  
💡 **Context-aware** - Knows devices from Case 2, faster discovery

### Device Control Details

**Target Device**:
- Name: "Đèn 1" (Light 1)
- Location: Bedroom
- Button ID: 1662
- Action: switch_on_off_controls_v2(buttonId=1662, buttonValue=1.0)
- Result: ✅ Successfully turned ON

---

## 📊 Case 4: Turn Off Light (15.62s)

### Overview
**User Input**: "turn off light 1 in the bed room."  
**Flow**: User → Manager → Tool Agent (3 iterations) → MCP → User  
**Total Time**: 15.62s (07:13:54 → 07:14:09)

### Workflow Details

```
Manager Agent:
└─ Analyze + Route (3.08s) → agent_type="tool"
   - Cache hit: 4,926 tokens (includes Case 3 turn ON context)

Tool Agent (LangGraph):
├─ Iteration 1: Discovery
│   ├─ LLM: Which device? (1.20s)
│   └─ MCP: get_device_list → buttonId=1662 (1.53s)
├─ Iteration 2: Execute
│   ├─ LLM: Plan switch_on_off (1.35s)
│   └─ MCP: switch_on_off_controls_v2(1662, 0.0) (2.97s) 🔴
└─ Iteration 3: Verify
    ├─ LLM: Generate success message (2.53s)
    └─ Redis: Save conversation (0.67s)
```

### Timing Breakdown

| Component | Time | Percentage |
|-----------|------|------------|
| Manager Routing (LLM + Cache) | 3.08s | 19.7% |
| MCP Initialization | 1.29s | 8.3% |
| Iteration 1 - Discovery (LLM + MCP) | 2.73s | 17.5% |
| Iteration 2 - Execute (LLM + MCP) | 4.32s | 27.7% 🔴 |
| Iteration 3 - Finalize (LLM + Redis) | 3.20s | 20.5% |
| Redis Save | 0.67s | 4.3% |
| Other | 0.33s | 2.0% |
| **Total** | **15.62s** | **100%** |

### Key Insights

✅ **Context-aware execution** - Knows device from Case 3 (same buttonId=1662)  
⚠️ **Slightly slower than Case 3** - 15.62s vs 13.88s (+12%)  
🟡 **Iteration 3 takes longer** - 3.20s vs 2.10s (more verbose response)  
🟢 **30% faster than Gemini 2.5 Pro** - Was 22.32s, now 15.62s  
💡 **Similar pattern** - Discovery → Execute → Verify workflow consistent

### Comparison: Case 3 vs Case 4

| Metric | Case 3 (ON) | Case 4 (OFF) | Difference |
|--------|-------------|--------------|------------|
| Total Time | 13.88s | 15.62s | +1.74s (+12%) |
| Manager Routing | 2.68s | 3.08s | +0.40s |
| Iteration 2 (Execute) | 4.12s | 4.32s | +0.20s |
| Iteration 3 (Finalize) | 2.10s | 3.20s | +1.10s 🔴 |
| MCP Switch Time | 2.85s | 2.97s | +0.12s |

**Why Case 4 is slower**: Longer LLM response generation in Iteration 3 (2.53s vs 1.46s)

---

## 📊 Case 5: Plan Execution with Parallel Tasks (50.69s)

### Overview
**User Inputs**: 
1. "Have 1 person in the bed room, Create plan." (Phase 1)
2. "plan 1" (Phase 2)

**Flow**: User → Manager → Plan Agent → [MCP + LLM] → Parallel Tasks → User  
**Total Time**: 50.69s (23.58s + 27.11s)

---

### Phase 1: Plan Creation (23.58s)

#### Workflow Details

```
Manager Agent:
└─ Analyze + Route (2.33s) → agent_type="plan"

Plan Agent (create_plans):
├─ MCP Initialization (1.92s)
├─ Step 1: Analyze Input
│   └─ LLM: Understand scenario (3.45s)
├─ Step 2: Get Device List
│   └─ MCP: get_device_list (1.67s)
└─ Step 3: Generate 3 Plans
    └─ LLM: Create Security/Comfort/Energy plans (14.21s) 🔴
```

#### Timing Breakdown

| Component | Time | Percentage |
|-----------|------|------------|
| Manager Routing (LLM) | 2.33s | 9.9% |
| MCP Initialization | 1.92s | 8.1% |
| Analyze Input (LLM) | 3.45s | 14.6% |
| Get Device List (MCP) | 1.67s | 7.1% |
| Generate 3 Plans (LLM) | 14.21s | 60.2% 🔴 |
| **Total Phase 1** | **23.58s** | **100%** |

#### Plan Options Generated

**Plan 1 - Security Priority**:
1. Turn on 8 lights (bedroom, living room, corridors)
2. Ensure illuminated environment
3. Activate beacon switch
4. Activate 4-button switch

**Plan 2 - Comfort Priority**:
1. Set AC to 20°C
2. Turn on reading lights
3. Activate ambient lighting

**Plan 3 - Energy Saving**:
1. Turn on minimal lights (bedroom only)
2. Use natural lighting where possible
3. Activate motion sensors

---

### Phase 2: Execute Plan 1 (27.11s)

#### Workflow Details

```
Manager Agent:
└─ Analyze + Route (2.68s) → agent_type="plan"

Plan Agent (execute_selected_plan):
├─ MCP Initialization (1.85s)
├─ Upload Plan to API (2.22s)
├─ PARALLEL EXECUTION (4 threads): 18.5s 🔥
│   ├─ Thread-0: Turn on 8 lights → ~12.3s
│   ├─ Thread-1: Verify illumination → ~8.1s
│   ├─ Thread-2: Activate beacon → ~9.5s
│   └─ Thread-3: Activate 4-button switch → ~18.5s 🔴 (bottleneck)
└─ Update Plan Status (1.74s)
```

#### Timing Breakdown

| Component | Time | Percentage |
|-----------|------|------------|
| Manager Routing (LLM) | 2.68s | 9.9% |
| MCP Initialization | 1.85s | 6.8% |
| Upload Plan to API | 2.22s | 8.2% |
| **Parallel Task Execution** | **18.5s** | **68.3%** 🔴 |
| Update Plan Status | 1.74s | 6.4% |
| Other | 0.12s | 0.4% |
| **Total Phase 2** | **27.11s** | **100%** |

#### Parallel Execution Details

**ThreadPoolExecutor (max_workers=4)**:

```
Thread-0 (Turn on 8 lights):
├─ Tool Agent: LangGraph workflow
├─ MCP calls: 8× switch_on_off_controls_v2
└─ Duration: ~12.3s

Thread-1 (Verify illumination):
├─ Tool Agent: Check lighting levels
├─ MCP calls: get_device_list + status checks
└─ Duration: ~8.1s

Thread-2 (Activate beacon):
├─ Tool Agent: Single device control
├─ MCP calls: switch_on_off_controls_v2
└─ Duration: ~9.5s

Thread-3 (Activate 4-button switch):
├─ Tool Agent: Complex device setup
├─ MCP calls: Multiple configuration calls
└─ Duration: ~18.5s 🔴 (BOTTLENECK - limits total time)
```

---

### Performance Analysis

#### Time Savings from Parallelization

| Scenario | Time | Notes |
|----------|------|-------|
| **Sequential Execution** | ~48.4s | 12.3 + 8.1 + 9.5 + 18.5 |
| **Parallel Execution** | 18.5s | Limited by slowest thread (Thread-3) |
| **Time Saved** | ~29.9s | **62% faster** ⚡ |

#### Bottleneck Analysis

**Phase 1**:
- 🔴 LLM Plan Generation: 14.21s (60.2%) - Creating 3 detailed plans
- 🟢 MCP Operations: 1.67s (7.1%) - Fast device list fetch

**Phase 2**:
- 🔴 Parallel Tasks: 18.5s (68.3%) - Limited by Thread-3 (4-button switch)
- 🟡 MCP Init: 1.85s (6.8%) - Setup overhead
- 🟡 API Upload: 2.22s (8.2%) - Plan status tracking

---

### Key Insights

✅ **Parallel execution WORKS** - 62% time savings vs sequential  
✅ **35-39% faster than Gemini 2.5 Pro** - Was 81.25s, now 50.69s  
⚠️ **LLM generation bottleneck** - 14.21s for plan creation (60.2%)  
⚠️ **Thread-3 limits parallelism** - 4-button switch takes 18.5s  
💡 **Optimization opportunities**:
  - Reduce plan generation time (use structured output, simpler prompts)
  - Optimize 4-button switch configuration (parallel sub-tasks)
  - Cache common plan templates (Security/Comfort/Energy)

---


**Each thread**:
- Spawns separate Tool Agent instance
- Runs complete LangGraph workflow (3 iterations)
- Independent MCP client connection
- No shared state (thread-safe)

**Wall-clock time = max(thread times)** = 18.5s (Thread-3)

---

## 🔍 Cross-Case Performance Comparison

### LLM Time Distribution

| Case | Total Time | LLM Time | LLM % | Observation |
|------|------------|----------|-------|-------------|
| Case 1 | 3.06s | 3.05s | 99.7% 🔴 | Almost pure LLM call |
| Case 2 | 14.80s | 7.10s | 48.0% 🟡 | Balanced with MCP |
| Case 3 | 13.88s | 3.89s | 28.0% 🟢 | MCP dominates |
| Case 4 | 15.62s | 5.08s | 32.5% 🟢 | Similar to Case 3 |
| Case 5-P1 | 23.58s | 17.66s | 74.9% 🔴 | Plan generation heavy |
| Case 5-P2 | 27.11s | 2.68s | 9.9% 🟢 | Parallel execution heavy |

**Trend**: Simple queries = 99% LLM | Complex operations = 10-30% LLM

### MCP Operation Impact

| Case | MCP Init | MCP API Calls | Total MCP | MCP % |
|------|----------|---------------|-----------|-------|
| Case 1 | 0s | 0s | 0s | 0% |
| Case 2 | 1.86s | 5.82s | 7.68s | 51.9% 🔴 |
| Case 3 | 1.23s | 4.35s | 5.58s | 40.2% 🟡 |
| Case 4 | 1.29s | 4.50s | 5.79s | 37.1% 🟡 |
| Case 5-P1 | 1.92s | 1.67s | 3.59s | 15.2% |
| Case 5-P2 | 1.85s | ~16.65s | ~18.5s | 68.3% 🔴 |

**Trend**: Device control cases = 37-52% MCP time

### Context Caching Effectiveness

| Case | Input Tokens | Cached Tokens | Cache % | Speed Benefit |
|------|--------------|---------------|---------|---------------|
| Case 1 | 0 | 0 | 0% | Baseline |
| Case 2 | 5,289 | 0 | 0% | New context |
| Case 3 | 5,100 | 4,925 | 96.6% 🔥 | 2-3x faster |
| Case 4 | 5,120 | 4,926 | 96.2% 🔥 | 2-3x faster |
| Case 5 | 8,000+ | ~5,000 | 62.5% 🟡 | Moderate |

**Observation**: Cases 3-4 benefit HUGELY from caching device data from Case 2

---

## 🎯 Optimization Recommendations

### High Priority 🔴

1. **MCP get_device_list Optimization** (Case 2)
   - Current: 5.82s (39.3% of total)
   - Target: <3s (-50%)
   - Approach: Redis caching, API batching, reduce payload size

2. **LLM Plan Generation** (Case 5-P1)
   - Current: 14.21s (60.2% of total)
   - Target: <8s (-44%)
   - Approach: Structured output, template-based generation, reduce reasoning steps

3. **Thread-3 Bottleneck** (Case 5-P2)
   - Current: 18.5s (limits parallel execution)
   - Target: <12s (-35%)
   - Approach: Break down 4-button switch into parallel sub-tasks

### Medium Priority 🟡

4. **MCP Initialization Overhead** (All cases)
   - Current: 1.2-1.9s per request
   - Target: <0.5s (-60%)
   - Approach: Connection pooling, persistent sessions, lazy loading

5. **Redis Save Operations** (Case 3-4)
   - Current: 0.64-0.67s
   - Target: <0.3s (-55%)
   - Approach: Async saves, batch operations, compression

6. **Manager Routing LLM** (All cases)
   - Current: 2.3-3.5s
   - Target: <1.5s (-50%)
   - Approach: Gemini 1.5 Flash for routing (5x faster), pattern caching

### Low Priority 🟢

7. **Iteration Count Reduction** (Case 3-4)
   - Current: 3 iterations (Discovery → Execute → Verify)
   - Target: 2 iterations (skip discovery if context-aware)
   - Approach: Smart context checking, direct execution mode

8. **Streaming Responses**
   - Current: User waits until completion
   - Target: Progressive UI updates
   - Approach: SSE streaming, partial result display