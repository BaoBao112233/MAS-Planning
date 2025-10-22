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

logger = logging.getLogger(__name__)

# Define AgentState for ToolAgent
class ToolState(TypedDict):
    input: str
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
        """Initialize MCP tools and LLM asynchronously"""
        self.tools = await self.get_mcp_tools()
        self.llm = ChatVertexAI(
            model_name=self.model,
            temperature=self.temperature,
            model_kwargs={
                "tools": self.tools
            },
            project=env.GOOGLE_CLOUD_PROJECT,
            location=env.GOOGLE_CLOUD_LOCATION
        )
        
        if self.verbose:
            logger.info(f"🔧 Loaded {len(self.tools)} MCP tools")
    
    async def get_mcp_tools(self):
        """Get tools from MCP server like PlanAgent"""
        try:
            async with MultiServerMCPClient({
                "mcp-server": {
                    "url": env.MCP_SERVER_URL,
                    "transport": "sse",
                }
            }) as client:
                tools = list(client.get_tools())
                return tools
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
        if any(keyword in input_text for keyword in ['list', 'available', 'tools', 'show']):
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
        
        if self.verbose:
            logger.info(f"🚀 Executing tool with query: {query}")
        
        if not self.llm:
            output = "❌ LLM not initialized. Please call init_async() first."
            return {**state, 'output': output, 'error': 'LLM not initialized'}
        
        try:
            # Use LLM with MCP tools to execute the task
            system_prompt = """You are a smart home automation assistant with access to MCP tools. 
            When given a task, use the appropriate tools to accomplish it.
            
            Available tool categories:
            - Device control tools
            - Room control tools  
            - Air conditioning control
            - Device status and information tools
            
            Respond with the tool execution result in a clear, user-friendly format."""
            
            messages = [
                SystemMessage(system_prompt),
                HumanMessage(query)
            ]
            
            # Convert to LangChain messages
            from template.message.converter import convert_messages_list
            lc_messages = convert_messages_list(messages)
            
            # Invoke LLM with tools
            response = self.llm.invoke(lc_messages)
            
            output = f"🔧 **Tool Execution Result:**\n\n{response.content}"
            
            if self.verbose:
                logger.info(f"✅ Tool execution completed successfully")
            
            return {**state, 'output': output}
            
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(f"❌ {error_msg}")
            
            # Fallback to mock execution for development
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
            logger.info(f'Entering {self.name}')
            logger.info(f'Query: {input_data}')
        
        # Handle different input types
        if isinstance(input_data, str):
            input_text = input_data
        elif isinstance(input_data, dict):
            input_text = input_data.get('input', input_data.get('message', ''))
        else:
            input_text = str(input_data)
        
        state = {
            'input': input_text,
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
