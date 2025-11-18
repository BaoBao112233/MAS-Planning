"""
Tool Agent for MAS-Planning system using direct API calls
No MCP dependency - calls api_things functions directly
"""
import logging
import asyncio
import json
from typing import Dict, Any, TypedDict, List, Optional, Callable
from termcolor import colored
from langgraph.graph import StateGraph, END
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import AIMessage, HumanMessage as LCHumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from template.configs.environments import env
from template.message.message import HumanMessage, SystemMessage
from template.message.converter import convert_messages_list
from template.agent.tool.prompt import TOOL_PROMPT

# Import api_things functions directly
from template.api_things.info_devices import get_device_list, get_device_info
from template.api_things.switch_devices import (
    switch_on_off_controls_v2,
    switch_on_off_all_device,
    switch_device_by_type,
    room_one_touch_control
)
from template.api_things.ac_devices import ac_controls_mesh_v2
from template.api_things.cronjob_devices import cronjob_device_v2

logger = logging.getLogger(__name__)


# =======================
#   Tool Agent State
# =======================
class ToolState(TypedDict):
    input: str
    messages: List[Any]
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    output: str
    error: str
    iteration: int
    max_iterations: int


# =======================
#   Pydantic schemas for tools
# =======================
class GetDeviceListInput(BaseModel):
    """No parameters needed"""
    pass

class SwitchOnOffControlsV2Input(BaseModel):
    buttonId: int = Field(description="ID of the button to control")
    data: int = Field(description="State to set (0 for off, 1 for on)")

class ACControlsMeshV2Input(BaseModel):
    buttonId: int = Field(description="ID of the remote button")
    power: str = Field(description="Power state: '1'/'on' for ON, '0'/'off' for OFF")
    mode: str = Field(default='1', description="AC mode: '1'/'auto', '2'/'heat', '3'/'cool', '4'/'dry', '5'/'fan'")
    temp: str = Field(default='24', description="Target temperature (16-32)")
    fan_speed: str = Field(default='0', description="Fan speed: '0'/'auto', '1'/'low', '2'/'medium', '3'/'high'")
    swing_h: str = Field(default='0', description="Horizontal swing: '1'/'on', '0'/'off'")
    swing_v: str = Field(default='0', description="Vertical swing: '1'/'on', '0'/'off'")

class CronjobDeviceV2Input(BaseModel):
    buttonId: int = Field(description="ID of the remotebutton")
    action: int = Field(description="Action: 1 for add/update, 3 for delete")
    job_status: int = Field(description="Job status: 0 for inactive, 1 for active")
    cron_time: str = Field(description="Cron expression: '* * * * * *' (second minute hour day month day_of_week)")
    button_code: str = Field(description="Button code: button01, button02, button03, button04")
    command: str = Field(description="Command: on, off, up, down, volume")
    issetting_online: bool = Field(description="Apply setting online")

class RoomOneTouchControlInput(BaseModel):
    room_id: str = Field(description="ID of the room")
    one_touch_code: str = Field(description="One-touch code: TURN_ON_ALL_DEVICES, TURN_OFF_ALL_DEVICES, TURN_ON_LIGHT, etc.")

class SwitchOnOffAllDeviceInput(BaseModel):
    command: str = Field(description="Command: on or off")

class SwitchDeviceByTypeInput(BaseModel):
    device_type: str = Field(description="Device type: LIGHT, TV, CONDITIONER, FAN, HOT_COLD_SHOWER, SOCKET")
    action: str = Field(description="Action: ON or OFF")


# =======================
#   Async Graph Executor
# =======================
class AsyncGraphExecutor:
    """Helper class to execute async graph nodes properly"""
    
    def __init__(self, agent):
        self.agent = agent
    
    def reason_node(self, state: ToolState) -> ToolState:
        """Synchronous node that executes async reasoning"""
        try:
            loop = asyncio.get_running_loop()
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(self.agent.reason_and_plan(state))
        except RuntimeError:
            return asyncio.run(self.agent.reason_and_plan(state))
    
    def execute_node(self, state: ToolState) -> ToolState:
        """Synchronous node that executes async tool execution"""
        try:
            loop = asyncio.get_running_loop()
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(self.agent.execute_tools_parallel(state))
        except RuntimeError:
            return asyncio.run(self.agent.execute_tools_parallel(state))


# =======================
#   Tool Agent Class
# =======================
class ToolAgent:
    """Tool Agent using direct API calls to api_things functions (NO MCP)"""

    def __init__(self, model="gemini-2.5-flash", temperature=0.2, verbose=False, max_iterations=5):
        self.name = "Tool Agent"
        self.model = model
        self.temperature = temperature
        self.verbose = verbose
        self.max_iterations = max_iterations
        self.tools = []
        self.tools_dict = {}
        self.llm = None
        self._graph = None
        self._executor = AsyncGraphExecutor(self)
        
        # Initialize tools immediately (no async needed)
        self._init_tools()
        self._init_llm()

    def _init_tools(self):
        """Initialize tools as LangChain StructuredTools wrapping api_things functions"""
        # Note: Tool execution IGNORES IR devices and related functions
        
        self.tools = [
            StructuredTool(
                name="get_device_list",
                description="Get status of all devices in the house. Returns list of rooms with devices and their current states. Use this first before any control operation.",
                func=self._sync_get_device_list,
                coroutine=self._async_get_device_list,
                args_schema=GetDeviceListInput
            ),
            StructuredTool(
                name="switch_on_off_controls_v2",
                description="Control on/off state of a switch device (LIGHT, FAN, TV, SOCKET, etc). Requires buttonId and data (0=off, 1=on). DO NOT use for IR-controlled devices.",
                func=self._sync_switch_on_off_controls_v2,
                coroutine=self._async_switch_on_off_controls_v2,
                args_schema=SwitchOnOffControlsV2Input
            ),
            StructuredTool(
                name="ac_controls_mesh_v2",
                description="Control air conditioner via BLE mesh. Requires buttonId, power, and optionally mode, temp, fan_speed, swing settings. DO NOT use for IR AC devices.",
                func=self._sync_ac_controls_mesh_v2,
                coroutine=self._async_ac_controls_mesh_v2,
                args_schema=ACControlsMeshV2Input
            ),
            StructuredTool(
                name="cronjob_device_v2",
                description="Create or update cronjob schedule for a device. Requires buttonId, action (1=add, 3=delete), job_status, cron_time, button_code, command. DO NOT use for IR devices.",
                func=self._sync_cronjob_device_v2,
                coroutine=self._async_cronjob_device_v2,
                args_schema=CronjobDeviceV2Input
            ),
            StructuredTool(
                name="room_one_touch_control",
                description="Execute room-level one-touch control (turn on/off all devices, lights, fans in a specific room). Requires room_id and one_touch_code.",
                func=self._sync_room_one_touch_control,
                coroutine=self._async_room_one_touch_control,
                args_schema=RoomOneTouchControlInput
            ),
            StructuredTool(
                name="switch_on_off_all_device",
                description="Turn on/off ALL devices in the entire house using one-touch control. Requires command (on/off).",
                func=self._sync_switch_on_off_all_device,
                coroutine=self._async_switch_on_off_all_device,
                args_schema=SwitchOnOffAllDeviceInput
            ),
            StructuredTool(
                name="switch_device_by_type",
                description="Turn on/off devices by type across the house (LIGHT, TV, FAN, etc). Requires device_type and action (ON/OFF).",
                func=self._sync_switch_device_by_type,
                coroutine=self._async_switch_device_by_type,
                args_schema=SwitchDeviceByTypeInput
            )
        ]
        
        self.tools_dict = {tool.name: tool for tool in self.tools}
        
        if self.verbose:
            logger.info(colored(f"🔧 Initialized {len(self.tools)} direct API tools", "green", attrs=["bold"]))

    def _init_llm(self):
        """Initialize Vertex LLM with tools"""
        logger.info(colored(f"Tool Agent using model: {self.model}", "green", attrs=["bold"]))

        base_llm = ChatVertexAI(
            model_name=self.model,
            temperature=self.temperature,
            project=env.GOOGLE_CLOUD_PROJECT,
            location=env.GOOGLE_CLOUD_LOCATION,
        )
        
        if self.tools:
            self.llm = base_llm.bind_tools(self.tools)
        else:
            self.llm = base_llm

    # ==========================================================
    # Wrapper functions for api_things (sync versions for StructuredTool.func)
    # ==========================================================
    def _sync_get_device_list(self) -> str:
        return asyncio.run(get_device_list())
    
    def _sync_switch_on_off_controls_v2(self, buttonId: int, data: int) -> str:
        return asyncio.run(switch_on_off_controls_v2(buttonId, data))
    
    def _sync_ac_controls_mesh_v2(self, buttonId: int, power: str, mode: str = '1', 
                                   temp: str = '24', fan_speed: str = '0', 
                                   swing_h: str = '0', swing_v: str = '0') -> str:
        return asyncio.run(ac_controls_mesh_v2(buttonId, power, mode, temp, fan_speed, swing_h, swing_v))
    
    def _sync_cronjob_device_v2(self, buttonId: int, action: int, job_status: int, 
                                 cron_time: str, button_code: str, command: str, 
                                 issetting_online: bool) -> str:
        return asyncio.run(cronjob_device_v2(buttonId, action, job_status, cron_time, 
                                               button_code, command, issetting_online))
    
    def _sync_room_one_touch_control(self, room_id: str, one_touch_code: str) -> str:
        return asyncio.run(room_one_touch_control(room_id, one_touch_code))
    
    def _sync_switch_on_off_all_device(self, command: str) -> str:
        return asyncio.run(switch_on_off_all_device(command))
    
    def _sync_switch_device_by_type(self, device_type: str, action: str) -> str:
        return asyncio.run(switch_device_by_type(device_type, action))
    
    # Async versions for StructuredTool.coroutine
    async def _async_get_device_list(self) -> str:
        return await get_device_list()
    
    async def _async_switch_on_off_controls_v2(self, buttonId: int, data: int) -> str:
        return await switch_on_off_controls_v2(buttonId, data)
    
    async def _async_ac_controls_mesh_v2(self, buttonId: int, power: str, mode: str = '1',
                                          temp: str = '24', fan_speed: str = '0',
                                          swing_h: str = '0', swing_v: str = '0') -> str:
        return await ac_controls_mesh_v2(buttonId, power, mode, temp, fan_speed, swing_h, swing_v)
    
    async def _async_cronjob_device_v2(self, buttonId: int, action: int, job_status: int,
                                        cron_time: str, button_code: str, command: str,
                                        issetting_online: bool) -> str:
        result = await cronjob_device_v2(buttonId, action, job_status, cron_time,
                                           button_code, command, issetting_online)
        return json.dumps(result) if isinstance(result, dict) else str(result)
    
    async def _async_room_one_touch_control(self, room_id: str, one_touch_code: str) -> str:
        return await room_one_touch_control(room_id, one_touch_code)
    
    async def _async_switch_on_off_all_device(self, command: str) -> str:
        return await switch_on_off_all_device(command)
    
    async def _async_switch_device_by_type(self, device_type: str, action: str) -> str:
        return await switch_device_by_type(device_type, action)

    async def init_async(self):
        """Compatibility method - no longer needed but kept for backward compatibility"""
        pass

    async def cleanup(self):
        """Compatibility method - no cleanup needed without MCP"""
        pass

    # ==========================================================
    # Core Async Logic
    # ==========================================================
    async def reason_and_plan(self, state: ToolState) -> ToolState:
        """LLM reasoning: phân tích input và quyết định tool calls"""
        if self.verbose:
            logger.info(colored(f"🧠 REASONING PHASE (Iteration {state['iteration']})", "green", attrs=["bold"]))
        
        try:
            messages = state.get("messages", [])
            if not messages:
                system_msg = SystemMessage(content=TOOL_PROMPT)
                # ✅ Inject token context into user message
                token_info = ""
                if state.get("token"):
                    token_info = f"[SYSTEM] Authentication token is available in the system context.\n\n"
                user_msg = HumanMessage(content=f"{token_info}User request: {state['input']}")
                messages = [system_msg, user_msg]
            
            # Call LLM with tools
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                self.llm.invoke,
                convert_messages_list(messages)
            )
            
            if self.verbose:
                logger.info(colored(f"💭 LLM Response: {response.content[:200]}...", "green", attrs=["bold"]))
                if hasattr(response, 'tool_calls') and response.tool_calls:
                    logger.info(colored(f"🔧 Tool calls planned: {len(response.tool_calls)}", "green", attrs=["bold"]))
                    for tc in response.tool_calls:
                        logger.info(colored(f"   → {tc['name']}({tc['args']})", "green", attrs=["bold"]))
            
            # Update state
            messages.append(response)
            state["messages"] = messages
            
            # ✅ FIX: Handle both tool_calls and final output properly
            if hasattr(response, 'tool_calls') and response.tool_calls:
                state["tool_calls"] = response.tool_calls
                # Clear output since we're not done yet
                state["output"] = ""
            else:
                # No more tool calls, this is the final answer
                state["tool_calls"] = []
                state["output"] = response.content
                
                if self.verbose:
                    logger.info(colored(f"✅ Final answer ready: {response.content[:100]}...", "green", attrs=["bold"]))
            
            return state
            
        except Exception as e:
            logger.error(f"❌ Reasoning error: {e}", exc_info=True)
            state["error"] = str(e)
            state["tool_calls"] = []
            state["output"] = f"Error during reasoning: {str(e)}"
            return state


    async def execute_tools_parallel(self, state: ToolState) -> ToolState:
        """Execute multiple tool calls with smart parallel/sequential logic - direct API calls"""
        if self.verbose:
            logger.info(colored(f"\n{'='*50}\n⚙️ EXECUTION PHASE\n{'='*50}", "green", attrs=["bold"]))
        
        tool_calls = state.get("tool_calls", [])
        if not tool_calls:
            return state
        
        independent_calls, dependent_calls = self._categorize_tool_calls(tool_calls)
        results = []
        
        # PHASE 1: Execute independent tools in parallel
        if independent_calls:
            if self.verbose:
                logger.info(colored(f"🚀 Phase 1: Executing {len(independent_calls)} independent tools in parallel", "green", attrs=["bold"]))
                for tc in independent_calls:
                    logger.info(colored(f"   → {tc['name']}", "green", attrs=["bold"]))

            parallel_results = await asyncio.gather(
                *[self._execute_single_tool(tc) for tc in independent_calls],
                return_exceptions=True
            )
            results.extend(parallel_results)
        
        # PHASE 2: Execute dependent tools
        if dependent_calls:
            prerequisite_tools = {"get_device_list"}
            prereqs = [tc for tc in dependent_calls if tc["name"] in prerequisite_tools]
            controls = [tc for tc in dependent_calls if tc["name"] not in prerequisite_tools]
            
            if prereqs:
                if self.verbose:
                    logger.info(colored(f"📋 Phase 2a: Executing {len(prereqs)} prerequisite tool(s) sequentially", "green", attrs=["bold"]))
                for tc in prereqs:
                    if self.verbose:
                        logger.info(colored(f"   → {tc['name']}", "green", attrs=["bold"]))
                    result = await self._execute_single_tool(tc)
                    results.append(result)
            
            if controls:
                if len(controls) == 1:
                    if self.verbose:
                        logger.info(colored(f"⚙️ Phase 2b: Executing 1 control tool", "green", attrs=["bold"]))
                        logger.info(colored(f"   → {controls[0]['name']}", "green", attrs=["bold"]))
                    result = await self._execute_single_tool(controls[0])
                    results.append(result)
                else:
                    if self.verbose:
                        logger.info(colored(f"⚡ Phase 2b: Executing {len(controls)} control tools in parallel", "green", attrs=["bold"]))
                        for tc in controls:
                            logger.info(colored(f"   → {tc['name']}", "green", attrs=["bold"]))

                    parallel_controls = await asyncio.gather(
                        *[self._execute_single_tool(tc) for tc in controls],
                        return_exceptions=True
                    )
                    results.extend(parallel_controls)
        
        # ✅ Add tool results as HumanMessage
        messages = state["messages"]
        tool_results_summary = []
        
        for result in results:
            if isinstance(result, dict):
                tool_name = result.get("tool_name", "unknown")
                content = result.get("content", {})
                success = result.get("success", False)
                
                if success:
                    # Format nicely for LLM
                    if isinstance(content, str):
                        tool_results_summary.append(f"✅ Tool '{tool_name}': {content}")
                    else:
                        tool_results_summary.append(f"✅ Tool '{tool_name}': {json.dumps(content, indent=2)}")
                else:
                    error_msg = content.get('error', 'Unknown error') if isinstance(content, dict) else str(content)
                    tool_results_summary.append(f"❌ Tool '{tool_name}' failed: {error_msg}")
            elif isinstance(result, Exception):
                logger.error(f"Tool execution exception: {result}")
                tool_results_summary.append(f"❌ Tool execution failed with exception: {str(result)}")
        
        # Add results as a single HumanMessage
        if tool_results_summary:
            results_text = "\n".join(tool_results_summary)
            messages.append(LCHumanMessage(content=f"[TOOL EXECUTION RESULTS]\n{results_text}"))
        
        state["messages"] = messages
        state["tool_results"] = results
        state["tool_calls"] = []
        state["iteration"] += 1
        
        if self.verbose:
            logger.info(colored(f"✅ Execution complete. Total results: {len(results)}", "green", attrs=["bold"]))
        
        return state

    def _categorize_tool_calls(self, tool_calls: List[Dict]) -> tuple:
        """Categorize tool calls: independent vs dependent (NO IR tools)"""
        independent = []
        dependent = []
        
        prerequisite_tools = {"get_device_list"}
        
        dependent_tools = {
            "switch_on_off_controls_v2",
            "ac_controls_mesh_v2",
            "cronjob_device_v2",
            "room_one_touch_control"
        }
        
        independent_tools = {
            "switch_on_off_all_device",
            "switch_device_by_type"
        }
        
        has_prerequisite = any(tc["name"] in prerequisite_tools for tc in tool_calls)
        
        for tc in tool_calls:
            tool_name = tc["name"]
            
            if tool_name in prerequisite_tools:
                dependent.insert(0, tc)
            elif tool_name in independent_tools:
                independent.append(tc)
            elif tool_name in dependent_tools:
                if has_prerequisite:
                    dependent.append(tc)
                else:
                    independent.append(tc)
            else:
                # Unknown tool - treat as dependent for safety
                dependent.append(tc)
        
        return independent, dependent

    async def _execute_single_tool(self, tool_call: Dict) -> Dict:
        """Execute a single tool call using direct API functions (NO MCP)"""
        try:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", "")
            
            if self.verbose:
                logger.info(colored(f"🔧 Calling {tool_name} with args: {tool_args}", "green", attrs=["bold"]))
            
            # Get tool from tools_dict
            tool = self.tools_dict.get(tool_name)
            if not tool:
                raise ValueError(f"Tool '{tool_name}' not found in available tools")
            
            # Call tool directly (uses coroutine if available)
            logger.info(colored(f"⏳ Invoking {tool_name} directly...", "green", attrs=["bold"]))
            
            # Call tool with timeout
            result = await asyncio.wait_for(
                tool.ainvoke(tool_args),
                timeout=60.0  # 60 seconds timeout
            )
            
            if self.verbose:
                logger.info(colored(f"✅ {tool_name} completed: {str(result)[:200]}...", "green", attrs=["bold"]))
            
            return {
                "tool_call_id": tool_id,
                "tool_name": tool_name,
                "content": result,
                "success": True
            }
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ Tool '{tool_name}' timed out after 60s")
            return {
                "tool_call_id": tool_call.get("id", ""),
                "tool_name": tool_call.get("name", "unknown"),
                "content": {"error": "Tool execution timed out after 60 seconds"},
                "success": False
            }
            
        except Exception as e:
            logger.error(f"❌ Tool execution error ({tool_call.get('name', 'unknown')}): {e}", exc_info=True)
            return {
                "tool_call_id": tool_call.get("id", ""),
                "tool_name": tool_call.get("name", "unknown"),
                "content": {"error": str(e)},
                "success": False
            }

    # ==========================================================
    # Router Logic
    # ==========================================================
    def should_continue(self, state: ToolState) -> str:
        """Decide whether to continue reasoning or finish"""
        if state["iteration"] >= state["max_iterations"]:
            if self.verbose:
                logger.warning(colored("🛑 Max iterations reached", "yellow", attrs=["bold"]))
            return "finish"
        
        if state.get("tool_calls"):
            return "execute"
        
        if state.get("output"):
            return "finish"
        
        if state.get("error"):
            return "finish"
        
        if state.get("tool_results"):
            return "reason"
        
        return "finish"

    # ==========================================================
    # Graph Construction
    # ==========================================================
    def create_graph(self):
        """Create LangGraph workflow"""
        g = StateGraph(ToolState)
        
        g.add_node("reason", self._executor.reason_node)
        g.add_node("execute", self._executor.execute_node)
        
        g.set_entry_point("reason")
        
        g.add_conditional_edges(
            "reason",
            self.should_continue,
            {
                "execute": "execute",
                "finish": END,
            }
        )
        
        g.add_conditional_edges(
            "execute",
            self.should_continue,
            {
                "reason": "reason",
                "finish": END,
            }
        )
        
        return g.compile(debug=False)  # Disable checkpoint logs for cleaner output
        # return g.compile(debug=self.verbose) --- IGNORE ---

    @property
    def graph(self):
        """Lazy load graph"""
        if self._graph is None:
            self._graph = self.create_graph()
        return self._graph

    # ==========================================================
    # Public Interface
    # ==========================================================
    async def ainvoke(self, input_data, **kwargs):
        """Async entry point for agent invocation - token no longer used in tool calls"""
        query = input_data["input"] if isinstance(input_data, dict) else input_data
        token = kwargs.get("token", "") or input_data.get("token", "")
        
        # Store token in env for api_things functions to use
        if token:
            env.OXII_API_KEY = token
        
        initial_state: ToolState = {
            "input": query,
            "token": token,  # Keep for backward compatibility
            "messages": [],
            "tool_calls": [],
            "tool_results": [],
            "output": "",
            "error": "",
            "iteration": 0,
            "max_iterations": self.max_iterations,
        }
        
        if self.verbose:
            logger.info(colored(f"🎯 NEW REQUEST: {query}", "green", attrs=["bold"]))
            logger.info(colored(f"🔑 ToolAgent using env.OXII_API_KEY: {env.OXII_API_KEY[:10] if env.OXII_API_KEY else 'None'}...", "green", attrs=["bold"]))
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self.graph.invoke,
            initial_state
        )
        
        if self.verbose:
            logger.info(colored(f"✨ FINAL OUTPUT: {result.get('output', 'No output')}", "green", attrs=["bold"]))
        
        return result

    def invoke(self, input_data, **kwargs):
        """Sync entry point (for backward compatibility)"""
        try:
            loop = asyncio.get_running_loop()
            raise RuntimeError(
                "invoke() called from async context. Use 'await agent.ainvoke()' instead."
            )
        except RuntimeError as e:
            if "no running event loop" in str(e).lower():
                return asyncio.run(self.ainvoke(input_data, **kwargs))
            else:
                raise


__all__ = ["ToolAgent"]