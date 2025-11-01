# Sequence Diagrams - Corrected Architecture Summary

## 🔧 Architectural Correction

### ❌ Previous (Incorrect)
- Showed **4 agents**: Manager Agent, Direct Agent, Plan Agent, Tool Agent
- "Direct Agent" participant in sequence diagrams
- Misunderstood Manager's internal direct response handling

### ✅ Current (Correct)  
- System has exactly **3 agents**: Manager Agent, Plan Agent, Tool Agent
- **NO separate Direct Agent exists**
- Manager Agent handles direct responses **internally** via routing logic

---

## 📊 Created Sequence Diagrams

### 1. **Case 1: Simple Greeting** (`sequence_Case1.mmd`)
**Flow**: Manager handles directly (no external agent)

**Key Points**:
- Manager's 3-node LangGraph: `analyze_query` → `delegate` → `finalize`
- `agent_type="direct"` triggers internal handling in `route_to_agent()`
- LLM returns `<direct_answer>` in reasoning_result
- NO external Direct Agent call

**Timing** (Total: 4.86s):
- Manager Analysis (LLM): **4.852s** ⚠️ BOTTLENECK
- Internal delegation: 0.001s
- Finalization: 0.001s

**Bottleneck**: Gemini 2.5 Pro routing decision

---

### 2. **Case 3: Turn On Device** (`sequence_Case3.mmd`)
**Flow**: Manager → Tool Agent (LangGraph workflow)

**Key Points**:
- Manager routes to Tool Agent (`agent_type="tool"`)
- Tool Agent uses **LangGraph with 3 iterations**:
  - **Iteration 0**: Reasoning → plan `get_device_list`
  - **Iteration 1**: Reasoning → plan `switch_on_off_v2`
  - **Iteration 2**: Reasoning → generate final output
- MCP connections: Fresh client per tool call for isolation
- Session management: Multiple SSE sessions for concurrent tools

**Timing** (Total: 29.91s):
- Manager Analysis (LLM): 8.498s
- Tool Init (MCP): 1.088s
- Iteration 0 Reasoning: **6.281s**
- Iteration 1 Reasoning: **7.778s**
- MCP Execution (switch): 2.347s
- Iteration 2 Finalize: **2.664s**

**Bottleneck**: Multiple LLM reasoning phases (16.723s total)

---

### 3. **Case 5: Plan Creation + Execution** (`sequence_Case5.mmd`)
**Flow**: Manager → Plan Agent → Tool Agent (2-phase lifecycle)

#### **Phase 1: Plan Creation** (45.39s)
**Steps**:
1. **Analyze Input**: LLM analyzes user intent (14.338s)
2. **Get Device List**: MCP `get_device_list` call (0.733s)
3. **Create 3 Plans**: LLM generates Security/Convenience/Energy plans (22.606s)
4. Return `plan_options` to user

**Timing Breakdown**:
- Manager Analysis: 6.157s
- Plan Init + MCP: 1.537s
- Step 1 (LLM): **14.338s**
- Step 2 (MCP): 0.733s
- Step 3 (LLM): **22.606s**

**Bottleneck**: LLM plan generation (36.944s total)

#### **Phase 2: Plan Execution** (59.66s)
**Steps**:
1. User selects "Plan 1" (Security Priority)
2. Manager routes to Plan Agent with `selected_plan_id=1`
3. Plan Agent executes 3 tasks sequentially via Tool Agent:
   - Task 1: Turn off Đèn trần (~20.18s)
   - Task 2: Turn off Đèn đọc sách (~17.61s)
   - Task 3: Turn on Đèn ngủ (~13.45s)
4. Each task uses Tool Agent's 3-iteration workflow

**Timing Breakdown**:
- Manager Analysis: 5.642s
- Plan Init: 1.529s
- Task executions: **51.24s** (3 tasks × ~17s avg)
- Finalization: 1.25s

**Bottleneck**: Sequential task execution (each task ~17s)

---

## 🏗️ Corrected Architecture Insights

### Manager Agent (`template/agent/manager/__init__.py`)
**Routing Logic** (`route_to_agent` method):
```python
if agent_type == 'direct':
    # Handle INTERNALLY - no external agent
    direct_answer = reasoning_result.get('direct_answer')
    delegation_result = {
        'output': direct_answer,
        'agent_type': 'direct',
        'success': True
    }
```

**LangGraph Nodes**:
1. `analyze_query`: LLM analyzes input with context → returns `agent_type`
2. `delegate`: Routes to Plan/Meta/Tool OR handles direct internally
3. `finalize`: Formats final response

### Tool Agent (`template/agent/tool/__init__.py`)
**LangGraph Workflow**:
```
START → reason_and_plan → [has tool_calls?] 
                              ↓ YES
                       execute_tools_parallel
                              ↓
                       reason_and_plan (next iteration)
                              ↓ NO tool_calls
                              END
```

**Key Features**:
- Fresh MCP client per tool call (session isolation)
- Parallel execution for independent tools
- Sequential execution for dependent tools (get_device_list → control)
- Smart categorization: prerequisite vs control tools

### Plan Agent (`template/agent/plan/__init__.py`)
**Two-Phase Lifecycle**:

**Phase 1 - create_plans()**:
1. Analyze user input (LLM)
2. Get device list (MCP)
3. Create 3 priority plans (LLM)
4. Return `plan_options` + `waiting_for_selection`

**Phase 2 - execute_selected_plan()**:
1. Select plan by ID (1=Security, 2=Convenience, 3=Energy)
2. For each task: Call Tool Agent
3. Update task status via API
4. Return execution summary

---

## 📉 Performance Bottleneck Analysis

### Overall Pattern
**LLM calls dominate execution time** across all cases:
- Case 1: 4.852s / 4.86s = **99.8%** LLM
- Case 3: 16.723s / 29.91s = **55.9%** LLM
- Case 5 Phase 1: 36.944s / 45.39s = **81.4%** LLM
- Case 5 Phase 2: ~35s / 59.66s = **58.7%** LLM

### Optimization Opportunities
1. **Cache Manager routing decisions** for similar queries
2. **Parallel tool execution** where possible (already implemented)
3. **Reduce LLM iterations** in Tool Agent (consider direct execution for simple commands)
4. **Batch plan tasks** in Plan Agent Phase 2 (parallel execution)
5. **Streaming responses** for better UX (hide latency)

---

## ✅ Verification Checklist

- [x] Case 1: NO Direct Agent shown
- [x] Case 3: Shows Tool Agent's LangGraph iterations
- [x] Case 5: Shows 2-phase Plan Agent lifecycle
- [x] All diagrams: Detailed timing breakdowns
- [x] All diagrams: Mermaid syntax validated
- [x] Architecture: Only 3 agents (Manager, Plan, Tool)
- [x] Code analysis: Matches implementation

---

## 📁 File Structure

```
docs/diagrams/
├── sequence_Case1.mmd  # Greeting - Manager direct
├── sequence_Case3.mmd  # Device Control - Manager→Tool
└── sequence_Case5.mmd  # Plan Lifecycle - Manager→Plan→Tool
```

**Generated**: 2025-01-31  
**Architecture**: Manager Agent + Plan Agent + Tool Agent (3 agents ONLY)  
**Status**: ✅ All corrected and validated
