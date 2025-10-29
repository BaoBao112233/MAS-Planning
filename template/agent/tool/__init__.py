"""
Tool Agent for MAS-Planning system using MCP tools
Enhanced version: fully async with proper event loop handling
"""
import logging
import asyncio
import json
from typing import Dict, Any, TypedDict, List, Optional, Callable
from termcolor import colored
from langgraph.graph import StateGraph, END
from langchain_google_vertexai import ChatVertexAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import AIMessage, HumanMessage as LCHumanMessage
from template.configs.environments import env
from template.message.message import HumanMessage, SystemMessage
from template.message.converter import convert_messages_list
from template.agent.tool.prompt import TOOL_PROMPT

logger = logging.getLogger(__name__)


# =======================
#   Tool Agent State
# =======================
class ToolState(TypedDict):
    input: str
    token: str
    messages: List[Any]
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    output: str
    error: str
    iteration: int
    max_iterations: int


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
    """Tool Agent sử dụng MCP để thực hiện smart home automation tasks với reasoning tự động"""

    def __init__(self, model="gemini-2.5-pro", temperature=0.2, verbose=False, max_iterations=5):
        self.name = "Tool Agent"
        self.model = model
        self.temperature = temperature
        self.verbose = verbose
        self.max_iterations = max_iterations
        self.tools = []
        self.tools_dict = {}  # Map tool names to tool objects
        self.llm = None
        self.mcp_client = None
        self._graph = None
        self._executor = AsyncGraphExecutor(self)

    # ==========================================================
    # Init MCP tools + Vertex LLM
    # ==========================================================
    async def init_async(self):
        """Load MCP tools and initialize Vertex LLM with persistent client"""
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            logger.warning(colored("nest_asyncio not installed. May have issues in nested event loops.", "yellow", attrs=["bold"]))
        
        self.mcp_client = MultiServerMCPClient(
            {"mcp-server": {"url": env.MCP_SERVER_URL, "transport": "sse"}}
        )
        await self.mcp_client.__aenter__()
        
        # Get tools (these are already LangChain tools)
        self.tools = list(self.mcp_client.get_tools())
        
        # Create tool lookup dictionary
        self.tools_dict = {tool.name: tool for tool in self.tools}
        
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

        if self.verbose:
            logger.info(colored(f"🔧 Loaded {len(self.tools)} MCP tools", "green", attrs=["bold"]))
            # for t in self.tools:
            #     logger.info(colored(f"🔹 {t.name} - {getattr(t, 'description', '')}"), "green", attrs=["bold"])

    async def cleanup(self):
        """Cleanup MCP client connection"""
        if self.mcp_client:
            await self.mcp_client.__aexit__(None, None, None)

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
            
            # Extract tool calls
            if hasattr(response, 'tool_calls') and response.tool_calls:
                state["tool_calls"] = response.tool_calls
            else:
                # No more tool calls, finish
                state["output"] = response.content
                state["tool_calls"] = []
            
            return state
            
        except Exception as e:
            logger.error(f"❌ Reasoning error: {e}", exc_info=True)
            state["error"] = str(e)
            state["tool_calls"] = []
            return state

    async def execute_tools_parallel(self, state: ToolState) -> ToolState:
        """Execute multiple tool calls with smart parallel/sequential logic"""
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
                *[self._execute_single_tool(tc, state["token"]) for tc in independent_calls],
                return_exceptions=True
            )
            results.extend(parallel_results)
        
        # PHASE 2: Execute dependent tools
        if dependent_calls:
            prerequisite_tools = {"get_device_list", "retrieve_ir_data_v2", "retrieve_ir_data"}
            prereqs = [tc for tc in dependent_calls if tc["name"] in prerequisite_tools]
            controls = [tc for tc in dependent_calls if tc["name"] not in prerequisite_tools]
            
            if prereqs:
                if self.verbose:
                    logger.info(colored(f"📋 Phase 2a: Executing {len(prereqs)} prerequisite tool(s) sequentially", "green", attrs=["bold"]))
                for tc in prereqs:
                    if self.verbose:
                        logger.info(colored(f"   → {tc['name']}", "green", attrs=["bold"]))
                    result = await self._execute_single_tool(tc, state["token"])
                    results.append(result)
            
            if controls:
                if len(controls) == 1:
                    if self.verbose:
                        logger.info(colored(f"⚙️ Phase 2b: Executing 1 control tool", "green", attrs=["bold"]))
                        logger.info(colored(f"   → {controls[0]['name']}", "green", attrs=["bold"]))
                    result = await self._execute_single_tool(controls[0], state["token"])
                    results.append(result)
                else:
                    if self.verbose:
                        logger.info(colored(f"⚡ Phase 2b: Executing {len(controls)} control tools in parallel", "green", attrs=["bold"]))
                        for tc in controls:
                            logger.info(colored(f"   → {tc['name']}", "green", attrs=["bold"]))

                    parallel_controls = await asyncio.gather(
                        *[self._execute_single_tool(tc, state["token"]) for tc in controls],
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
        """Phân loại tool calls: độc lập vs phụ thuộc based on 13 OXII tools"""
        independent = []
        dependent = []
        
        prerequisite_tools = {
            "get_device_list",
            "retrieve_ir_data_v2", 
            "retrieve_ir_data"
        }
        
        dependent_tools = {
            "switch_on_off_controls_v2",
            "ac_controls_mesh_v2",
            "ac_controls_mesh",
            "open_ir_send_for_testing_mesh_v2",
            "open_ir_send_for_testing_mesh",
            "cronjob_device_v2",
            "cronjob_device",
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
                dependent.append(tc)
        
        return independent, dependent

    async def _execute_single_tool(self, tool_call: Dict, token: str) -> Dict:
        """Execute a single tool call using fresh MCP client per call"""
        temp_client = None
        try:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", "")
            
            # ✅ Inject token into args
            tool_args["token"] = token
            
            if self.verbose:
                logger.info(colored(f"🔧 Calling {tool_name} with args: {tool_args}", "green", attrs=["bold"]))
            
            # ✅ FIX: Create fresh MCP client for each tool call
            # This avoids SSE connection deadlock in nested async contexts
            logger.info(colored(f"⏳ Creating fresh MCP client for {tool_name}...", "green", attrs=["bold"]))

            temp_client = MultiServerMCPClient(
                {"mcp-server": {"url": env.MCP_SERVER_URL, "transport": "sse"}}
            )
            
            # Enter context and get tools
            await temp_client.__aenter__()
            temp_tools = list(temp_client.get_tools())
            temp_tools_dict = {t.name: t for t in temp_tools}
            
            # Get the tool
            tool = temp_tools_dict.get(tool_name)
            if not tool:
                raise ValueError(f"Tool '{tool_name}' not found in available tools")
            
            # Call tool with timeout
            logger.info(colored(f"⏳ Invoking {tool_name}...", "green", attrs=["bold"]))
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
            
        finally:
            # Always cleanup temp client
            if temp_client:
                try:
                    await temp_client.__aexit__(None, None, None)
                    logger.info(colored(f"🧹 Cleaned up MCP client for {tool_call.get('name', 'unknown')}", "green", attrs=["bold"]))
                except Exception as cleanup_error:
                    logger.warning(colored(f"⚠️ Error cleaning up MCP client: {cleanup_error}", "yellow", attrs=["bold"]))

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
        
        return g.compile(debug=self.verbose)

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
        """Async entry point for agent invocation"""
        token = kwargs.get("token", "")
        query = input_data["input"] if isinstance(input_data, dict) else input_data
        
        initial_state: ToolState = {
            "input": query,
            "token": token,
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