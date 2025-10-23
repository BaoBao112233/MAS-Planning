"""
Tool Agent for MAS-Planning system using MCP tools
"""
import logging
import json
import asyncio
from typing import Dict, List, Any, Optional, TypedDict
from langchain_core.runnables.graph import MermaidDrawMethod
from langgraph.graph import StateGraph, END

from template.message.message import HumanMessage, SystemMessage
from template.configs.environments import env
from langchain_google_vertexai import ChatVertexAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from template.agent.tool.prompt import TOOL_PROMPT
from termcolor import colored

logger = logging.getLogger(__name__)

# Define AgentState for ToolAgent
class ToolState(TypedDict):
    input: str
    token: str
    route: str
    output: str
    tool_data: Dict[str, Any]
    error: str

class ToolAgent:
    """Tool Agent sử dụng MCP server để thực hiện smart home automation tasks"""
    
    def __init__(self, model: str = "gemini-2.5-pro", temperature: float = 0.2, verbose: bool = False):
        self.name = 'Tool Agent'
        self.model = model
        self.temperature = temperature
        self.verbose = verbose
        self.tools = []
        self.llm = None
        self.graph = self.create_graph()
        
        if self.verbose:
            logger.info(f"✅ {self.name} initialized")
    
    async def init_async(self):
        self.tools = await self.get_mcp_tools()
        base_llm = ChatVertexAI(
            model_name=self.model,
            temperature=self.temperature,
            project=env.GOOGLE_CLOUD_PROJECT,
            location=env.GOOGLE_CLOUD_LOCATION
        )
        
        # Bind tools to LLM for proper tool calling
        if self.tools:
            self.llm = base_llm.bind_tools(self.tools)
        else:
            self.llm = base_llm
        
        if self.verbose:
            logger.info(f"🔧 Loaded {len(self.tools)} MCP tools")
            logger.info(f"🤖 LLM initialized with tools: {len(self.tools) > 0}")
    
    async def get_mcp_tools(self):
        """Get tools from MCP server like PlanAgent"""
        try:
            # Add timeout for MCP connection
            async with asyncio.timeout(5):  # 5 second timeout
                async with MultiServerMCPClient({
                    "mcp-server": {
                        "url": env.MCP_SERVER_URL,
                        "transport": "sse",
                    }
                }) as client:
                    tools = list(client.get_tools())
                    return tools
        except asyncio.TimeoutError:
            logger.error(f"❌ MCP connection timeout after 5 seconds")
            return []
        except Exception as e:
            logger.error(f"❌ MCP connection failed: {str(e)}")
            return []
    
    def router(self, state: ToolState):
        """Route input to appropriate action"""
        input_value = state.get('input', '') or ''
        input_text = input_value.lower() if input_value else ''
        
        if self.verbose:
            logger.info(f"🔍 Routing input: {input_text}")
        
        # Determine route based on input content
        # Priority: Check for device-related requests first
        if any(keyword in input_text for keyword in ['device', 'room', 'living room', 'bedroom', 'kitchen', 'switch', 'control', 'turn on', 'turn off', 'air conditioner']):
            route = 'execute_tool'
        elif any(keyword in input_text for keyword in ['list tools', 'available tools', 'show tools', 'what tools']) and 'device' not in input_text:
            route = 'list_tools'
        elif any(keyword in input_text for keyword in ['search', 'find']):
            route = 'search_tools'
        elif any(keyword in input_text for keyword in ['info', 'detail', 'describe']):
            route = 'get_tool_info'
        elif any(keyword in input_text for keyword in ['help', 'how']):
            route = 'help_with_tool'
        else:
            # Default to execute_tool for any device control task
            route = 'execute_tool'
        
        if self.verbose:
            logger.info(f"📍 Routed to: {route}")
        
        return {**state, 'route': route}
    
    def list_tools(self, state: ToolState):
        """List all available MCP tools"""
        if not self.tools:
            output = "❌ No MCP tools available. Please check MCP server connection."
        else:
            output = f"📋 Available MCP Tools ({len(self.tools)}):\n\n"
            for i, tool in enumerate(self.tools, 1):
                tool_name = getattr(tool, 'name', 'Unknown Tool')
                tool_desc = getattr(tool, 'description', 'No description available')
                output += f"{i}. **{tool_name}**\n   {tool_desc}\n\n"
        
        return {**state, 'output': output}
    
    def search_tools(self, state: ToolState):
        """Search tools by keyword"""
        query = state.get('input', '')
        search_keywords = self.extract_search_keywords(query)
        
        if not search_keywords:
            output = "❌ Please provide keywords to search for tools."
            return {**state, 'output': output}
        
        matching_tools = []
        for tool in self.tools:
            tool_name = getattr(tool, 'name', '')
            tool_desc = getattr(tool, 'description', '')
            
            for keyword in search_keywords:
                if (keyword.lower() in tool_name.lower() or 
                    keyword.lower() in tool_desc.lower()):
                    matching_tools.append({
                        'tool': tool,
                        'match_reason': 'name' if keyword.lower() in tool_name.lower() else 'description'
                    })
                    break
        
        if not matching_tools:
            output = f"❌ No tools found matching: {', '.join(search_keywords)}"
        else:
            output = f"🔍 Found {len(matching_tools)} tools matching '{', '.join(search_keywords)}':\n\n"
            for match in matching_tools:
                tool = match['tool']
                tool_name = getattr(tool, 'name', 'Unknown')
                tool_desc = getattr(tool, 'description', 'No description')
                match_reason = match['match_reason']
                output += f"• **{tool_name}** (matched by {match_reason})\n  {tool_desc}\n\n"
        
        return {**state, 'output': output}
    
    def get_tool_info(self, state: ToolState):
        """Get detailed information about a specific tool"""
        query = state.get('input', '')
        tool_name = self.extract_tool_name(query)
        
        if not tool_name:
            output = "❌ Please specify which tool you want information about."
            return {**state, 'output': output}
        
        # Find the tool
        target_tool = None
        for tool in self.tools:
            if getattr(tool, 'name', '').lower() == tool_name.lower():
                target_tool = tool
                break
        
        if not target_tool:
            output = f"❌ Tool '{tool_name}' not found."
            return {**state, 'output': output}
        
        # Format tool information
        tool_name = getattr(target_tool, 'name', 'Unknown')
        tool_desc = getattr(target_tool, 'description', 'No description available')
        
        output = f"🔧 **{tool_name}**\n\n"
        output += f"**Description:** {tool_desc}\n\n"
        
        # Add parameter information if available
        input_schema = getattr(target_tool, 'inputSchema', {})
        if input_schema:
            properties = input_schema.get('properties', {})
            required = input_schema.get('required', [])
            
            if properties:
                output += "**Parameters:**\n"
                for param_name, param_info in properties.items():
                    param_type = param_info.get('type', 'unknown')
                    param_desc = param_info.get('description', 'No description')
                    required_text = " (required)" if param_name in required else ""
                    output += f"  • `{param_name}` ({param_type}){required_text}: {param_desc}\n"
        
        return {**state, 'output': output}
    
    def execute_tool(self, state: ToolState):
        """Execute tool using LLM with MCP tools"""
        query = state.get('input', '')
        token = state.get('token', '')
        
        if self.verbose:
            logger.info(f"🚀 Executing tool with query: {query}")
            logger.info(f"� Using token: {token[:10]}..." if token else "🔑 No token provided")
            logger.info(f"🔧 Available tools: {len(self.tools)}")
            logger.info(f"🤖 LLM initialized: {self.llm is not None}")
        
        if not self.llm:
            output = "❌ LLM not initialized. Please call init_async() first."
            return {**state, 'output': output, 'error': 'LLM not initialized'}
        
        if not self.tools:
            output = "❌ No MCP tools available. Please check MCP server connection."
            return {**state, 'output': output, 'error': 'No MCP tools'}
        
        try:
            # Build system prompt with token information
            system_prompt = TOOL_PROMPT
            if token:
                system_prompt += f"\n\nIMPORTANT: When calling MCP tools that require a 'token' parameter, use this authentication token: {token}"
            
            messages = [
                SystemMessage(system_prompt),
                HumanMessage(query)
            ]
            
            # Convert to LangChain messages
            from template.message.converter import convert_messages_list
            lc_messages = convert_messages_list(messages)
            
            # Invoke LLM with tools
            response = self.llm.invoke(lc_messages)
            
            if self.verbose:
                logger.info(f"🔍 LLM response type: {type(response)}")
                logger.info(f"🔍 LLM response: {response}")
                if hasattr(response, 'content'):
                    logger.info(f"🔍 LLM response content: '{response.content}'")
                if hasattr(response, 'tool_calls'):
                    logger.info(f"🔍 LLM tool calls: {response.tool_calls}")
            
            # Handle tool calls if present
            if hasattr(response, 'tool_calls') and response.tool_calls:
                # Process tool calls and get results
                tool_results = []
                for tool_call in response.tool_calls:
                    try:
                        # Execute the tool call through MCP
                        tool_name = tool_call['name']
                        tool_args = tool_call['args']
                        
                        if self.verbose:
                            logger.info(f"🔧 Executing tool: {tool_name} with args: {tool_args}")
                        
                        # Find the tool in our MCP tools
                        matching_tool = None
                        for tool in self.tools:
                            if tool.name == tool_name:
                                matching_tool = tool
                                break
                        
                        if matching_tool:
                            # Execute tool directly 
                            import asyncio
                            import concurrent.futures
                            
                            async def call_tool_async():
                                """Call the tool asynchronously with fresh MCP connection"""
                                try:
                                    # Get token from state
                                    token = state.get('token', '')
                                    if token:
                                        tool_args['token'] = token
                                    
                                    logger.info(f"🔧 Calling tool {tool_name} with args: {tool_args}")
                                    
                                    # Create fresh MCP client connection for each tool call
                                    async with MultiServerMCPClient({
                                        "mcp-server": {
                                            "url": env.MCP_SERVER_URL,
                                            "transport": "sse",
                                        }
                                    }) as client:
                                        # Get fresh tools from client
                                        fresh_tools = list(client.get_tools())
                                        
                                        # Find matching tool in fresh tools
                                        fresh_tool = None
                                        for tool in fresh_tools:
                                            if tool.name == tool_name:
                                                fresh_tool = tool
                                                break
                                        
                                        if not fresh_tool:
                                            return f"Tool {tool_name} not found in fresh MCP connection"
                                        
                                        logger.info(f"🔧 Using fresh tool: {type(fresh_tool)}")
                                        
                                        # Call the fresh tool
                                        result = await fresh_tool.ainvoke(tool_args)
                                        logger.info(f"✅ Fresh tool call successful: {type(result)}")
                                        logger.info(f"✅ Result preview: {str(result)[:200]}...")
                                        return result
                                        
                                except Exception as e:
                                    import traceback
                                    error_details = traceback.format_exc()
                                    error_msg = f"Tool call failed: {str(e)}\nDetails: {error_details}"
                                    logger.error(f"❌ Tool call error: {error_msg}")
                                    return error_msg
                            
                            def run_async_tool():
                                """Run async tool in proper event loop"""
                                try:
                                    # Check if we're already in an event loop
                                    try:
                                        loop = asyncio.get_running_loop()
                                        logger.info("🔄 Using existing event loop")
                                        # Create a new task in the existing loop
                                        import concurrent.futures
                                        with concurrent.futures.ThreadPoolExecutor() as executor:
                                            future = executor.submit(asyncio.run, call_tool_async())
                                            return future.result(timeout=30)
                                    except RuntimeError:
                                        # No running loop, create a new one
                                        logger.info("🆕 Creating new event loop")
                                        return asyncio.run(call_tool_async())
                                except Exception as e:
                                    import traceback
                                    error_details = traceback.format_exc()
                                    error_msg = f"Async execution failed: {str(e)}\nDetails: {error_details}"
                                    logger.error(f"❌ Async execution error: {error_msg}")
                                    return error_msg
                            
                            try:
                                # Execute tool using the async wrapper
                                result = run_async_tool()
                                    
                                if self.verbose:
                                    logger.info(f"🔍 Tool result type: {type(result)}")
                                    logger.info(f"🔍 Tool result: {result}")
                                    
                                # Process result - handle different response formats
                                if isinstance(result, str):
                                    # Handle string results (common for MCP tools)
                                    if result.startswith("Tool call failed:"):
                                        tool_results.append(f"**{tool_name}**: {result}")
                                    else:
                                        # Try to parse as JSON for prettier display
                                        try:
                                            import json
                                            parsed = json.loads(result)
                                            if isinstance(parsed, list) and len(parsed) > 0:
                                                # Format device list nicely
                                                devices_info = []
                                                for room in parsed:
                                                    room_name = room.get('room_name', 'Unknown Room')
                                                    devices = room.get('devices', [])
                                                    buttons = room.get('buttons', [])
                                                    
                                                    devices_info.append(f"🏠 **{room_name}**:")
                                                    for device in devices:
                                                        devices_info.append(f"  📱 {device.get('name', 'Unknown Device')} ({device.get('device_status', 'Unknown Status')})")
                                                    for button in buttons:
                                                        devices_info.append(f"  🔘 {button.get('name', 'Unknown Button')} ({button.get('button_type', 'Unknown Type')}) - {button.get('status', 'Unknown Status')}")
                                                
                                                formatted_result = "\n".join(devices_info)
                                                tool_results.append(f"**{tool_name}**: \n{formatted_result}")
                                            else:
                                                tool_results.append(f"**{tool_name}**: {json.dumps(parsed, indent=2, ensure_ascii=False)}")
                                        except (json.JSONDecodeError, TypeError):
                                            # Not JSON, display as-is
                                            tool_results.append(f"**{tool_name}**: {result}")
                                elif isinstance(result, dict):
                                    if 'content' in result:
                                        # Extract actual content
                                        content = result['content']
                                        if isinstance(content, list) and len(content) > 0:
                                            # Handle array of content objects
                                            if isinstance(content[0], dict) and 'text' in content[0]:
                                                tool_results.append(f"**{tool_name}**: {content[0]['text']}")
                                            else:
                                                tool_results.append(f"**{tool_name}**: {str(content[0])}")
                                        else:
                                            tool_results.append(f"**{tool_name}**: {str(content)}")
                                    else:
                                        tool_results.append(f"**{tool_name}**: {str(result)}")
                                else:
                                    tool_results.append(f"**{tool_name}**: {str(result)}")
                                    
                            except Exception as e:
                                tool_results.append(f"**{tool_name}**: Tool execution failed: {str(e)}")
                                if self.verbose:
                                    logger.error(f"❌ Tool execution error: {e}")
                            
                            if self.verbose:
                                logger.info(f"✅ Tool {tool_name} executed directly")
                        else:
                            tool_results.append(f"**{tool_name}**: Tool not found")
                            if self.verbose:
                                logger.warning(f"⚠️ Tool {tool_name} not found in available tools")
                                
                    except Exception as e:
                        tool_results.append(f"**{tool_call['name']}**: Error - {str(e)}")
                        if self.verbose:
                            logger.error(f"❌ Tool execution failed: {str(e)}")
                
                # Combine results
                if tool_results:
                    output = f"🔧 **Tool Execution Result:**\n\n" + "\n\n".join(tool_results)
                else:
                    output = f"🔧 **Tool Execution Result:**\n\nNo tool results available"
            else:
                # No tool calls, use response content
                output = f"🔧 **Tool Execution Result:**\n\n{response.content}"
            
            if self.verbose:
                logger.info(f"✅ Tool execution completed successfully")
                logger.info(f"📝 Response length: {len(response.content)}")
            
            return {**state, 'output': output}
            
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"❌ {error_msg}")

            output = f"🧪 **Mock Tool Execution** (LLM unavailable):\n\n"
            output += f"Task: {query}\n"
            output += f"Status: ✅ Simulated execution completed\n"
            output += f"Result: Mock response for development purposes\n"
            output += f"Note: {error_msg}"
            
            return {**state, 'output': output, 'error': error_msg}
    
    def help_with_tool(self, state: ToolState):
        """Provide help and guidance for tool usage"""
        output = """🆘 **Tool Agent Help**
        
        Available commands:
        • Natural language device control (e.g., "turn on living room lights")
        • Room control (e.g., "turn off all devices in bedroom")
        • AC control (e.g., "set air conditioner to 22 degrees")
        • Device status (e.g., "get list of all devices")

        Examples:
        • "turn on light 1"
        • "set AC to cool mode 24 degrees"
        • "turn off all devices in living room"
        • "get device status"

        The system will automatically select and execute the appropriate MCP tools based on your request.
        """
        return {**state, 'output': output}
    
    def extract_search_keywords(self, query: str) -> List[str]:
        """Extract search keywords from query"""
        keywords = []
        query_lower = query.lower()
        
        # Remove common words
        stop_words = {'search', 'for', 'find', 'tool', 'tools', 'the', 'a', 'an', 'with', 'that', 'can'}
        words = query_lower.split()
        
        for word in words:
            if word not in stop_words and len(word) > 2:
                keywords.append(word)
        
        return keywords
    
    def extract_tool_name(self, query: str) -> str:
        """Extract tool name from query"""
        query_lower = query.lower()
        
        # Check available tools
        for tool in self.tools:
            tool_name = getattr(tool, 'name', '')
            if tool_name.lower() in query_lower:
                return tool_name
        
        return ""
    
    def controller(self, state: ToolState):
        """Controller for graph routing"""
        return state.get('route', 'execute_tool')
    
    def create_graph(self):
        """Create execution graph for ToolAgent"""
        workflow = StateGraph(ToolState)
        
        # Add nodes
        workflow.add_node('router', self.router)
        workflow.add_node('list_tools', self.list_tools)
        workflow.add_node('search_tools', self.search_tools)
        workflow.add_node('get_tool_info', self.get_tool_info)
        workflow.add_node('execute_tool', self.execute_tool)
        workflow.add_node('help_with_tool', self.help_with_tool)
        
        # Set entry point
        workflow.set_entry_point('router')
        
        # Add conditional edges
        workflow.add_conditional_edges('router', self.controller)
        
        # All nodes end
        workflow.add_edge('list_tools', END)
        workflow.add_edge('search_tools', END)
        workflow.add_edge('get_tool_info', END)
        workflow.add_edge('execute_tool', END)
        workflow.add_edge('help_with_tool', END)
        
        return workflow.compile(debug=self.verbose)
    
    def invoke(self, input_data, **kwargs) -> Dict[str, Any]:
        """Execute tool agent with input query"""
        if self.verbose:
            logger.info(colored(f'Entering: {self.name}', 'cyan'))
            logger.info(colored(f'Query: {input_data}', 'cyan'))
        
        # Extract token from kwargs or input_data
        token = kwargs.get('token', '')
        
        # Handle different input types
        if isinstance(input_data, str):
            input_text = input_data
        elif isinstance(input_data, dict):
            input_text = input_data.get('input', input_data.get('message', ''))
            token = input_data.get('token', token)  # Prefer token from input_data if available
        else:
            input_text = str(input_data)
        
        state = {
            'input': input_text,
            'token': token,
            'route': '',
            'tool_data': {},
            'error': '',
            'output': ''
        }
        
        try:
            result = self.graph.invoke(state)
            output = result.get('output', '')
            route = result.get('route', '')
            error = result.get('error', '')
            
            if self.verbose:
                logger.info(f'Route: {route}')
                logger.info(f'Output: {output}')
            
            return {
                'route': route,
                'output': output,
                'available_tools': len(self.tools),
                'tool_agent_result': True,
                'error': error
            }
        
        except Exception as e:
            error_msg = f"Error in ToolAgent execution: {str(e)}"
            logger.error(error_msg)
            return {
                'route': 'error',
                'output': f"❌ {error_msg}",
                'available_tools': len(self.tools),
                'tool_agent_result': False,
                'error': str(e)
            }
    
    def stream(self, input_data):
        """Streaming interface (placeholder)"""
        return self.invoke(input_data)

# Export the ToolAgent
__all__ = ["ToolAgent"]
