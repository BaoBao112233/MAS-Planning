from template.agent.tool.utils import (
    extract_tools_from_module,
    update_tool_to_module,
    save_tool_to_module,
    remove_tool_from_module,
    read_markdown_file
)
from langchain_google_vertexai import ChatVertexAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.runnables.graph import MermaidDrawMethod
from template.message import HumanMessage,SystemMessage
from template.agent.tool.state import AgentState
from template.configs.environments import env
from langgraph.graph import StateGraph,END
from importlib import import_module,reload
from IPython.display import display,Image
from template.router import LLMRouter
from template.agent import BaseAgent
from termcolor import colored
from subprocess import run
import ast
import os
import logging

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ToolAgent(BaseAgent):
    def __init__(self, 
                 model: str = "gemini-2.5-pro", 
                 temperature: float = 0.2, 
                 verbose: bool = False,
                 max_iteration: int = 10):
        super().__init__()

        self.name = "Tool Agent"
        self.tools = []
        self.temperature = temperature
        self.verbose = verbose

        self.llm = None

        logger.info(f"ToolAgent initialized with model={model}, temperature={temperature}")

        self.max_iteration = max_iteration
        self.verbose = verbose
        self.api_client = None  # Placeholder for API client
        
        # Initialize graph
        self.graph = self.create_graph()

    async def init_async(self):
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
    
    async def get_mcp_tools(self):
        async with MultiServerMCPClient({
            "mcp-server": {
                # make sure you start your weather server on port 8000
                "url": env.MCP_SERVER_URL,
                "transport": "sse",
            }
        }) as client:
            tools = list(client.get_tools())
            return tools
    
    def router(self, state: AgentState):
        # Convert custom messages to LangChain messages before passing to LLM
        messages = convert_messages_list(state['messages'])
        llm_response=self.llm.invoke(messages)
        if self.verbose:
            logger.info(colored(f"LLM Response: {llm_response.content}",'cyan'))
        return {**state,'messages':[HumanMessage(llm_response.content)]}