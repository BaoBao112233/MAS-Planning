from typing import TypedDict, List, Dict, Any, Optional
from template.message.message import BaseMessage


class ToolState(TypedDict):
    """Enhanced state for autonomous reasoning agent"""
    # Input
    input: str
    token: str
    
    # Conversation context
    messages: List[Any]  # List of HumanMessage, AIMessage, ToolMessage
    
    # Tool execution
    tool_calls: List[Dict[str, Any]]  # Pending tool calls from LLM
    tool_results: List[Dict[str, Any]]  # Results from executed tools
    
    # Output
    output: str
    error: str
    
    # Control flow
    iteration: int  # Current iteration count
    max_iterations: int  # Max iterations before stopping


class AgentState(TypedDict):
    """Legacy state for backward compatibility"""
    input: str
    token: str
    route: str
    tool_data: dict
    error: str
    output: str