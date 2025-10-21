import os
import re
import json
import logging

from langchain_google_vertexai import ChatVertexAI
from langchain.tools import StructuredTool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain.agents import AgentExecutor
from langgraph import StateGraph, START, END
from langgraph.graph import MessagesState

from template.configs.environments import get_environment_variables
from template.schemas.model import (
    ChatRequest, 
    ChatResponse,
    ResponseFormatter
)
from template.agent.histories import RedisSupportChatHistory
from template.configs.environments import env
from abc import ABC,abstractmethod



# Set environment variables for Google Cloud authentication
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(env.GOOGLE_APPLICATION_CREDENTIALS)
os.environ["GOOGLE_CLOUD_PROJECT"] = env.GOOGLE_CLOUD_PROJECT


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

memories = {}    

class Agent:

    def __init__(self, model: str = "gemini-2.5-pro", temperature: float = 0.2):
        try:
            # Load credentials từ service account file
            credentials_path = os.path.abspath(env.GOOGLE_APPLICATION_CREDENTIALS)

            if not os.path.exists(credentials_path):
                raise FileNotFoundError(f"Service account file not found: {credentials_path}")


            # Khởi tạo LLM
            self.llm = ChatVertexAI(
                model_name=model,
                temperature=temperature,
                project=env.GOOGLE_CLOUD_PROJECT,
                location=env.GOOGLE_CLOUD_LOCATION
            )

            logger.info(f"Initialized ChatVertexAI with model={model}, project={env.GOOGLE_CLOUD_PROJECT}, location={env.GOOGLE_CLOUD_LOCATION}")
        except Exception as e:
            logger.error(f"Error initializing ChatVertexAI: {str(e)}")
            raise

        # Tools
        self.tools = []

        # Prompt template
        self.prompt = []
        self.default_session_id = 0

    def _get_memory(self, session_id: str, conversation_id: str) -> RedisSupportChatHistory:
        """Get or create memory for a session"""    
        session_key = str(session_id)
        if session_key not in memories:
            # Create directory if it doesn't exist
            os.makedirs("memories", exist_ok=True)
            memories[session_key] = RedisSupportChatHistory(
                session_id=session_id,
                conversation_id=conversation_id
            )

            # Initialize with user ID if it's a new session
            if not memories[session_key].exists_session():
                memories[session_key].add_ai_message(
                    f"Here we go! Your Conversation ID is {conversation_id} and I will never give it out again. "
                    f"It's just for getting more info from the tool get_list_phone_numbers and create_incident "
                    f"with input conversation_id = {conversation_id}."
                )

        return memories[session_key]
