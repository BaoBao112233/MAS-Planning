"""
Manager Agent - Central coordinator for the Multi-Agent System (MAS)

The Manager Agent serves as the entry point and orchestrator for the entire MAS system.
It analyzes user queries, makes routing decisions, and coordinates interactions between
specialized agents (Plan Agent, Meta Agent, Tool Agent).
"""

import json
from template.agent import BaseAgent
from template.configs.environments import env
from template.agent.manager.state import ManagerState
from template.agent.manager.prompt import MANAGER_PROMPT
from template.agent.manager.utils import (
    extract_manager_response,
    classify_query_type,
    format_final_response,
    extract_plan_selection,
    validate_agent_result,
    get_agent_capabilities
)
from template.agent.manager.fast_path import get_fast_path_classifier
from template.message.message import HumanMessage, SystemMessage
from template.message.converter import convert_messages_list
from template.agent.histories import RedisSupportChatHistory

from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph, END, START
from termcolor import colored
import logging
import time
import json
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


class ManagerAgent(BaseAgent):
    """
    Manager Agent - Central coordinator for the Multi-Agent System
    
    Responsibilities:
    1. Analyze and classify user queries
    2. Make intelligent routing decisions
    3. Delegate tasks to appropriate specialized agents
    4. Coordinate multi-agent workflows
    5. Format and deliver final responses
    """
    
    def __init__(self, 
                 session_id: str,
                 conversation_id: str,
                 model: str = "gemini-2.5-flash", 
                 temperature: float = 0.2, 
                 max_iteration: int = 5,
                 verbose: bool = False,
                 llm=None):
        super().__init__()
        
        self.name = "Manager Agent"
        
        # Chat history for conversation context
        self.session_id = session_id
        self.chat_history = RedisSupportChatHistory(
            session_id=session_id,
            conversation_id=conversation_id,
            ttl=env.TTL_SECONDS
        )

        logger.info(colored(f"Manager Agent using model: {model}", "green", attrs=["bold"]))

        # LLM configuration
        if llm:
            self.llm = llm
        else:
            self.llm = ChatVertexAI(
                model_name=model,
                temperature=temperature,
                project=env.GOOGLE_CLOUD_PROJECT,
                location=env.GOOGLE_CLOUD_LOCATION
            )
        
        self.max_iteration = max_iteration
        self.verbose = verbose
        self.system_prompt = MANAGER_PROMPT
        
        # Lazy-loaded agents
        self._plan_agent = None
        self._tool_agent = None
        
        # Session state for plan persistence
        self._cached_plan_options = {}
        
        # Fast-path classifier for optimization
        self.fast_path = get_fast_path_classifier(verbose=self.verbose)
        self.use_fast_path = True  # Enable/disable fast-path optimization
        self.fast_path_threshold = 0.90  # Confidence threshold for fast-path
        
        # Create execution graph
        self.graph = self.create_graph()
        
        if self.verbose:
            logger.info(f"✅ {self.name} initialized successfully")
            logger.info(f"⚡ Fast-path optimization: {'enabled' if self.use_fast_path else 'disabled'}")
    
    @property
    def plan_agent(self):
        """Lazy load Plan Agent"""
        if self._plan_agent is None:
            from template.agent.plan import PlanAgent
            self._plan_agent = PlanAgent(verbose=self.verbose, model=env.PLAN_MODEL_NAME)
            
            # Initialize async components
            try:
                import asyncio
                import threading
                
                def run_async_init():
                    # Create new event loop in separate thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self._plan_agent.init_async())
                        logger.info("📋 Plan Agent initialized with LLM")
                    except Exception as e:
                        logger.warning(colored(f"⚠️ Plan Agent async init failed: {e}"), 'yellow')
                    finally:
                        loop.close()
                
                # Run in separate thread to avoid event loop conflict
                thread = threading.Thread(target=run_async_init)
                thread.start()
                thread.join(timeout=10)  # Wait max 10 seconds
                
                if thread.is_alive():
                    logger.warning(colored("⚠️ Plan Agent async init timeout"), 'yellow')
                    
            except Exception as e:
                logger.warning(colored(f"⚠️ Could not init Plan Agent async: {e}"), 'yellow')
                logger.info("🧪 Plan Agent will use fallback mode")
            
            logger.info("📋 Plan Agent loaded")
        return self._plan_agent
    
    @property
    def tool_agent(self):
        """Lazy load Tool Agent"""
        if self._tool_agent is None:
            from template.agent.tool import ToolAgent
            self._tool_agent = ToolAgent(verbose=self.verbose, model=env.TOOL_MODEL_NAME)
            # Initialize ToolAgent async components
            try:
                import asyncio
                import threading
                
                def run_async_init():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self._tool_agent.init_async())
                    finally:
                        loop.close()
                
                thread = threading.Thread(target=run_async_init)
                thread.start()
                thread.join(timeout=10)
                
                if thread.is_alive():
                    logger.warning(colored("⚠️ ToolAgent async init timeout"), 'yellow')
                    
            except Exception as e:
                logger.warning(colored(f"⚠️ Could not init ToolAgent async: {e}"), 'yellow')
            
            logger.info("🔧 Tool Agent loaded")
        return self._tool_agent
    
    def _detect_and_convert_empty_room(self, user_input: str) -> Optional[tuple[str, str]]:
        """
        Detect if query indicates empty room and auto-convert to turn off command
        
        Returns:
            tuple[str, str] | None: (converted_command, detected_info) if detected, None otherwise
        """
        user_input_lower = user_input.lower()
        
        # Keywords for empty room detection
        empty_keywords = [
            "0 person", "no one", "nobody", "no people", "0 people",
            "không có ai", "have 0", "no have", "empty room", "empty"
        ]
        
        # Check if query contains empty room keywords
        has_empty_keyword = any(keyword in user_input_lower for keyword in empty_keywords)
        
        if not has_empty_keyword:
            return None
        
        # Detect if specific room mentioned or entire house
        # Let Tool Agent handle room extraction from actual device list
        if any(word in user_input_lower for word in ['house', 'home', 'nhà', 'toàn bộ', 'all rooms']):
            converted_command = "Turn off all devices in the entire house"
            detected_info = "entire house"
        else:
            # Generic conversion - Tool Agent will extract specific room from device list
            converted_command = f"Turn off all devices - {user_input}"
            detected_info = "room (to be identified from device list)"
        
        if self.verbose:
            logger.info(colored(f"🔴 EMPTY ROOM DETECTED!", "red", attrs=["bold"]))
            logger.info(colored(f"   Original: {user_input}", "yellow"))
            logger.info(colored(f"   Converted: {converted_command}", "green", attrs=["bold"]))
            logger.info(colored(f"   Scope: {detected_info}", "cyan"))
        
        return (converted_command, detected_info)
    
    def analyze_query(self, state: ManagerState) -> ManagerState:
        """
        Analyze user query and determine routing strategy with conversation context
        Uses fast-path optimization for high-confidence device control commands
        """
        user_input = state.get('input', '')
        token = state.get('token', '')
        
        if self.verbose:
            logger.info(f"🔍 Analyzing query: {user_input}")
        
        # ========================================
        # HIGHEST PRIORITY: EMPTY ROOM DETECTION
        # Auto-convert empty room queries to turn off commands
        # ========================================
        empty_room_result = self._detect_and_convert_empty_room(user_input)
        if empty_room_result:
            converted_command, detected_info = empty_room_result
            
            # Override user input with converted command
            state['input'] = converted_command
            state['original_input'] = user_input  # Keep original for reference
            state['empty_room_detected'] = True
            state['detected_scope'] = detected_info
            
            # Force routing to tool agent
            return {
                **state,
                'agent_type': 'tool',
                'query_type': 'device_control',
                'confidence_score': 1.0,
                'fast_path_used': True,
                'empty_room_auto_conversion': True,
                'reasoning_result': {
                    'reasoning': f'Empty room detected: {detected_info}. Auto-converting to turn off all devices for energy saving. Tool Agent will identify specific rooms from device list.',
                    'agent_type': 'tool',
                    'confidence': 1.0,
                    'explanation': f'Empty room auto-routing: {user_input} → {converted_command}'
                }
            }
        
        # ========================================
        # FAST-PATH OPTIMIZATION
        # Try pattern-based classification first
        # ========================================
        if self.use_fast_path:
            fast_result = self.fast_path.classify(user_input, token)
            if fast_result and fast_result.confidence >= self.fast_path_threshold:
                if self.verbose:
                    logger.info(colored(f"⚡ FAST-PATH ACTIVATED", "green", attrs=["bold"]))
                    logger.info(colored(f"   Intent: {fast_result.intent.value}", "green"))
                    logger.info(colored(f"   Execution Path: {fast_result.execution_path.value}", "green"))
                    logger.info(colored(f"   Confidence: {fast_result.confidence:.2f}", "green"))
                    logger.info(colored(f"   Skipped: Manager LLM call (~2-3s saved)", "yellow", attrs=["bold"]))
                
                # Map execution path to agent_type for backward compatibility
                agent_type_map = {
                    'tool_then_manager': 'tool',
                    'manager_only': 'direct',
                    'full_planning': 'plan'
                }
                agent_type = agent_type_map.get(fast_result.execution_path.value, 'direct')
                
                # Build fast-path state
                return {
                    **state,
                    'agent_type': agent_type,
                    'query_type': fast_result.intent.value,
                    'confidence_score': fast_result.confidence,
                    'fast_path_used': True,
                    'fast_path_result': fast_result,
                    'reasoning_result': {
                        'reasoning': fast_result.reasoning,
                        'agent_type': agent_type,
                        'confidence': fast_result.confidence,
                        'explanation': f"Fast-path: {fast_result.intent.value} → {fast_result.execution_path.value}"
                    }
                }
        
        # ========================================
        # STANDARD LLM-BASED ANALYSIS
        # Fall back to LLM when fast-path doesn't match
        # ========================================
        if self.verbose:
            logger.info("🤖 Using LLM analysis (no fast-path match)")
        
        # Build messages with conversation history
        messages = []
        
        # Add system prompt
        messages.append(SystemMessage(self.system_prompt))
        
        # Add conversation history for context
        if self.chat_history.messages:
            # Add last few messages for context (limit to prevent token overflow)
            recent_messages = self.chat_history.messages[-6:]  # Last 6 messages (3 exchanges)
            
            # Convert chat history messages to our custom format for consistency
            for msg in recent_messages:
                if hasattr(msg, 'content'):
                    content = msg.content
                    if hasattr(msg, '__class__'):
                        if 'Human' in msg.__class__.__name__:
                            messages.append(HumanMessage(f"Previous User: {content}"))
                        elif 'AI' in msg.__class__.__name__:
                            messages.append(SystemMessage(f"Previous AI: {content}"))
            
            if self.verbose:
                logger.info(f"📚 Using {len(recent_messages)} previous messages for context")
        
        # Add current user query
        messages.append(HumanMessage(f"Current User Query: {user_input}"))
        
        try:
            # Convert and invoke LLM
            lc_messages = convert_messages_list(messages)
            llm_response = self.llm.invoke(lc_messages)
            
            # Extract structured response
            reasoning_result = extract_manager_response(llm_response.content)
            
            if self.verbose:
                logger.info(f"🎯 Routing decision: {reasoning_result['agent_type']} (confidence: {reasoning_result['confidence']:.2f})")
                logger.info(f"📝 Reasoning: {reasoning_result['reasoning'][:100]}...")
            
            # Classify query type for additional context
            query_type = classify_query_type(user_input)
            
            # Update state
            return {
                **state,
                'messages': messages,
                'reasoning_result': reasoning_result,
                'agent_type': reasoning_result['agent_type'],
                'query_type': query_type,
                'confidence_score': reasoning_result['confidence']
            }
            
        except Exception as e:
            logger.error(f"❌ Error in query analysis: {str(e)}")
            
            # Enhanced fallback routing that considers context
            fallback_type = self._context_aware_fallback_routing(user_input)
            
            return {
                **state,
                'messages': messages,
                'reasoning_result': {
                    'reasoning': f'Fallback routing due to analysis error: {str(e)}',
                    'agent_type': fallback_type,
                    'confidence': 0.3,
                    'explanation': f'Using fallback routing to {fallback_type} agent'
                },
                'agent_type': fallback_type,
                'query_type': classify_query_type(user_input),
                'confidence_score': 0.3
            }
    
    def _context_aware_fallback_routing(self, query: str) -> str:
        """Enhanced fallback routing that considers conversation context"""
        query_lower = query.lower().strip()
        
        # Priority 1: Check for explicit plan creation keywords (highest priority)
        if any(word in query_lower for word in ['create plan', 'make plan', 'plan', 'create', 'setup', 'automate']):
            return 'plan'
        
        # Priority 2: Check conversation history for context clues
        if self.chat_history.messages:
            recent_messages = self.chat_history.messages[-4:]  # Last 4 messages for context
            
            # Look for patterns indicating this is a response to an AI question
            for i, msg in enumerate(recent_messages):
                if hasattr(msg, 'content') and 'AI' in msg.__class__.__name__:
                    content = msg.content.lower()
                    
                    # AI asked about device control parameters
                    if any(word in content for word in ['mode', 'temperature', 'brightness', 'color', 'speed']):
                        # User is likely providing parameters -> route to tool
                        if any(word in query_lower for word in ['default', 'auto', 'high', 'low', 'medium', 'on', 'off']):
                            return 'tool'
                    
                    # AI presented plan options
                    if any(word in content for word in ['plan', 'option', 'choose', 'select']):
                        # User is likely selecting a plan
                        if any(word in query_lower for word in ['1', '2', '3', 'plan', 'option', 'first', 'second', 'third']):
                            return 'plan'
                    
                    # AI asked for clarification about device control
                    if any(word in content for word in ['which', 'what', 'where', 'how']):
                        # Check if previous context was about devices
                        if i > 0 and hasattr(recent_messages[i-1], 'content'):
                            prev_content = recent_messages[i-1].content.lower()
                            if any(word in prev_content for word in ['turn', 'set', 'control', 'adjust', 'device']):
                                return 'tool'
        
        # Priority 3: Fall back to standard keyword-based routing
        return self._fallback_routing(query)
    
    def _fallback_routing(self, query: str) -> str:
        """Simple fallback routing when LLM analysis fails"""
        query_lower = query.lower()
        query_type = classify_query_type(query)
        
        # Priority 1: Plan creation (highest priority)
        if any(word in query_lower for word in ['create plan', 'plan', 'create', 'setup', 'automate', 'automation']):
            return 'plan'
        
        # Priority 2: Plan selection
        elif query_type == 'selection':
            return 'plan'
        
        # Priority 3: Device control
        elif any(word in query_lower for word in ['turn', 'set', 'control', 'adjust']):
            return 'tool'
        
        # Default to direct for other requests
        else:
            return 'direct'
    
    def route_to_agent(self, state: ManagerState) -> ManagerState:
        """
        Route request to appropriate specialized agent
        """
        agent_type = state.get('agent_type', 'direct')
        user_input = state.get('input', '')
        
        if self.verbose:
            logger.info(f"📍 route_to_agent state keys: {list(state.keys())}")
            logger.info(f"📍 fast_path_result in state: {'fast_path_result' in state}")
            if 'fast_path_result' in state:
                fpr = state['fast_path_result']
                logger.info(f"📍 fast_path_result type: {type(fpr)}")
                if fpr:
                    logger.info(f"📍 fast_path_result has extracted_params: {hasattr(fpr, 'extracted_params')}")
        
        # Validate and normalize agent type (only support: direct, plan, tool)
        valid_agents = ['direct', 'plan', 'tool']
        if agent_type not in valid_agents:
            logger.warning(colored(f"⚠️ Invalid agent type '{agent_type}', mapping to valid agent", 'yellow'))
            # Map unknown types to closest valid agent
            if 'plan' in agent_type.lower() or 'meta' in agent_type.lower():
                agent_type = 'plan'
            elif 'tool' in agent_type.lower() or 'device' in agent_type.lower() or 'control' in agent_type.lower():
                agent_type = 'tool'
            else:
                agent_type = 'direct'
            logger.info(f"📍 Remapped to: {agent_type} agent")
        
        if self.verbose:
            logger.info(f"🚀 Routing to {agent_type} agent")
        
        try:
            delegation_result = None  # Initialize to avoid UnboundLocalError
            
            if agent_type == 'direct':
                # Check if this is show_device_status intent
                query_type = state.get('query_type', 'general')
                fast_path_result = state.get('fast_path_result')
                
                if query_type == 'show_device_status' or (fast_path_result and hasattr(fast_path_result, 'intent') and fast_path_result.intent.value == 'show_device_status'):
                    # Special handling for show_device_status
                    # Manager calls get_device_list directly
                    if self.verbose:
                        logger.info(colored("📋 Show Device Status - Manager calling get_device_list", "cyan", attrs=["bold"]))
                    
                    token = state.get('token', '')
                    device_list = self._get_device_list(token)
                    
                    if self.verbose:
                        logger.info(f"📊 Device list type: {type(device_list)}")
                        if device_list:
                            if isinstance(device_list, dict):
                                logger.info(f"📊 Device list keys: {device_list.keys()}")
                            elif isinstance(device_list, list):
                                logger.info(f"📊 Device list length: {len(device_list)}")
                                if len(device_list) > 0:
                                    logger.info(f"📊 First item type: {type(device_list[0])}")
                                    logger.info(f"📊 First item: {device_list[0]}")
                            else:
                                logger.info(f"📊 Device list value: {device_list}")
                    
                    if device_list:
                        # Wrap list in expected dict structure for formatter
                        if isinstance(device_list, list):
                            device_data = {'data': {'rooms': device_list}}
                        else:
                            device_data = device_list
                        
                        if self.verbose:
                            logger.info(f"📦 Device data for formatter: {type(device_data)}")
                        
                        # Get params from fast_path_result
                        if fast_path_result and hasattr(fast_path_result, 'extracted_params'):
                            params = fast_path_result.extracted_params
                            if self.verbose:
                                logger.info(f"🎯 Using fast_path params: {params}")
                        else:
                            params = {'room': 'all', 'show_all': True}
                            if self.verbose:
                                logger.info(f"⚠️ No fast_path params, using default: {params}")
                                if fast_path_result:
                                    logger.info(f"⚠️ fast_path_result exists but no extracted_params attr")
                                    logger.info(f"⚠️ fast_path_result type: {type(fast_path_result)}")
                                    logger.info(f"⚠️ fast_path_result attrs: {dir(fast_path_result)}")
                        
                        # Format response using fast_path classifier with user query for language detection
                        user_query = state.get('input', '')
                        formatted_response = self.fast_path.format_device_status_response(device_data, params, user_query)
                        
                        if self.verbose:
                            logger.info(f"✅ Formatted response length: {len(formatted_response)}")
                            logger.info(f"✅ Formatted response preview: {formatted_response[:200]}...")
                        
                        delegation_result = {
                            'output': formatted_response,
                            'agent_type': 'direct',
                            'success': True,
                            'device_list': device_list
                        }
                    else:
                        delegation_result = {
                            'output': '❌ Không thể lấy thông tin thiết bị. Vui lòng thử lại.',
                            'agent_type': 'direct',
                            'success': False,
                            'error': 'Failed to get device list'
                        }
                else:
                    # Handle other direct responses
                    reasoning_result = state.get('reasoning_result', {})
                    direct_answer = reasoning_result.get('direct_answer')
                    
                    if not direct_answer:
                        # Provide default helpful response based on query type
                        if query_type == 'information':
                            direct_answer = """🏠 **Smart Home Information**

A smart home is a residence equipped with internet-connected devices that enable remote monitoring and management of appliances and systems, such as lighting, heating, security, and entertainment systems.

**Key Benefits:**
• **Convenience**: Control devices remotely via apps or voice commands
• **Energy Efficiency**: Automated scheduling and optimization
• **Security**: Real-time monitoring and alerts
• **Comfort**: Personalized automation based on preferences

**How I Can Help:**
• Create customized automation plans (security, convenience, or energy-focused)
• Control smart home devices in real-time
• Provide guidance on smart home setup and optimization

What would you like to know more about?"""
                        else:
                            direct_answer = """🤖 **Smart Home Assistant**

I'm your Multi-Agent Smart Home Assistant! I can help you with:

🏗️ **Planning**: Create comprehensive smart home automation plans
🔧 **Control**: Manage and control your smart devices
🧠 **Analysis**: Provide strategic insights for home automation
📋 **Guidance**: Answer questions and provide recommendations

**Popular Commands:**
• "Create a smart home plan for my bedroom"
• "Turn on the living room lights"
• "Set the air conditioner to 22 degrees"
• "What's the best way to automate my home?"

How can I assist you today?"""
                    
                    delegation_result = {
                        'output': direct_answer,
                        'direct_answer': direct_answer,  # Add this for format_final_response
                        'agent_type': 'direct',
                        'success': True
                    }
                
            elif agent_type == 'plan':
                # Load cached plan options from context if available
                context = state.get('context', {})
                if 'cached_plan_options' in context:
                    self._cached_plan_options = context['cached_plan_options']
                    if self.verbose:
                        logger.info(f"📋 Loaded cached plan options: {list(self._cached_plan_options.keys())}")
                
                # Check if this is a plan selection
                plan_selection = extract_plan_selection(user_input)
                query_type = state.get('query_type', '')
                
                # Extract token from state for PlanAgent authentication
                token = state.get('token', '')
                
                if (plan_selection and self._cached_plan_options) or query_type == 'selection':
                    # User is selecting from previously generated plans
                    if plan_selection:
                        delegation_result = self.plan_agent.invoke(
                            user_input, 
                            selected_plan_id=plan_selection,
                            plan_options=self._cached_plan_options,
                            token=token
                        )
                    else:
                        # Try to extract plan number from query_type selection
                        fallback_selection = extract_plan_selection(user_input) or 1
                        delegation_result = self.plan_agent.invoke(
                            user_input,
                            selected_plan_id=fallback_selection,
                            plan_options=self._cached_plan_options,
                            token=token
                        )
                else:
                    # New planning request
                    # Pass Manager's analysis to PlanAgent to avoid duplicate LLM analysis
                    analysis = state.get('reasoning_result') or {}
                    
                    # Enhance analysis with room extraction
                    user_input_lower = user_input.lower()
                    rooms_mentioned = []
                    
                    # Extract rooms from user input
                    room_keywords = {
                        'bedroom': ['bedroom', 'bed room', 'phòng ngủ'],
                        'living room': ['living room', 'living', 'phòng khách'],
                        'kitchen': ['kitchen', 'nhà bếp', 'bếp'],
                        'bathroom': ['bathroom', 'toilet', 'nhà vệ sinh', 'phòng tắm'],
                        'dining room': ['dining', 'phòng ăn']
                    }
                    
                    for room_name, keywords in room_keywords.items():
                        if any(kw in user_input_lower for kw in keywords):
                            rooms_mentioned.append(room_name)
                    
                    # Build enhanced analysis
                    enhanced_analysis = {
                        'reasoning': analysis.get('reasoning', ''),
                        'agent_type': analysis.get('agent_type', 'plan'),
                        'confidence': analysis.get('confidence', 1.0),
                        'primary_intent': user_input,
                        'key_requirements': [user_input],
                        'scope': {
                            'rooms': rooms_mentioned if rooms_mentioned else [],
                            'device_types': [],
                            'all_house': ('all' in user_input_lower or 'whole house' in user_input_lower)
                        },
                        'context': {
                            'time_of_day': 'unknown',
                            'situation': 'general',
                            'urgency': 'normal'
                        },
                        'priority_hints': {
                            'security': 33,
                            'convenience': 33,
                            'energy': 34
                        }
                    }
                    
                    if self.verbose:
                        logger.info(f"📊 Passing enhanced analysis to PlanAgent:")
                        logger.info(f"   - Rooms detected: {rooms_mentioned if rooms_mentioned else 'None (will use all rooms)'}")
                        logger.info(f"   - All house: {enhanced_analysis['scope']['all_house']}")
                        logger.info(f"   - Primary intent: {enhanced_analysis.get('primary_intent', 'N/A')[:100]}")
                    
                    delegation_result = self.plan_agent.invoke(user_input, token=token, input_analysis=enhanced_analysis)
                    
                    # Cache plan options for future selections
                    if delegation_result.get('plan_options'):
                        self._cached_plan_options = delegation_result['plan_options']
                
            elif agent_type == 'tool':
                # Route to Tool Agent with token
                token = state.get('token', '')
                if self.verbose:
                    logger.info(f"🔧 Routing to ToolAgent with token: {token[:10] if token else 'None'}...")
                
                # Ensure input is in proper format with token
                tool_input = {
                    'input': user_input,
                    'token': token
                }
                
                # Call ToolAgent ainvoke since invoke raises error in async context
                import asyncio
                import concurrent.futures
                import traceback
                
                def call_tool_agent(input_data):
                    return asyncio.run(self.tool_agent.ainvoke(input_data))
                
                try:
                    loop = asyncio.get_running_loop()
                    # In async context, run in thread to avoid event loop conflict
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(call_tool_agent, tool_input)
                        delegation_result = future.result()
                except RuntimeError as e:
                    # No running loop, can run directly
                    if "no running event loop" in str(e).lower():
                        delegation_result = call_tool_agent(tool_input)
                    else:
                        # Re-raise other RuntimeErrors
                        logger.error(f"❌ RuntimeError in Tool Agent execution: {str(e)}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        raise
                
            else:
                # Unknown agent type
                delegation_result = {
                    'output': f'Unknown agent type: {agent_type}',
                    'success': False,
                    'error': f'Agent type {agent_type} not recognized'
                }
            
            # Validate result
            if not validate_agent_result(delegation_result, agent_type):
                logger.warning(colored(f"⚠️ Invalid result from {agent_type} agent"), 'yellow')
                delegation_result = {
                    'output': 'I apologize, but there was an issue processing your request.',
                    'success': False,
                    'error': f'Invalid result from {agent_type} agent'
                }
            
            return {
                **state,
                'delegation_result': delegation_result
            }
            
        except Exception as e:
            import traceback
            logger.error(f"❌ Error routing to {agent_type} agent: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
            delegation_result = {
                'output': f'I encountered an error while processing your request: {str(e)}',
                'success': False,
                'error': str(e)
            }
            
            return {
                **state,
                'delegation_result': delegation_result
            }
    
    def finalize_response(self, state: ManagerState) -> ManagerState:
        """
        Format and finalize the response for the user
        """
        delegation_result = state.get('delegation_result', {})
        agent_type = state.get('agent_type', 'direct')
        user_input = state.get('input', '')
        
        if self.verbose:
            logger.info(f"📝 Finalizing response from {agent_type} agent")
        
        try:
            # Format the final response
            final_answer = format_final_response(delegation_result, agent_type, user_input)
            
            # Add metadata for debugging if verbose
            if self.verbose and agent_type != 'direct':
                reasoning = state.get('reasoning_result', {}).get('reasoning', '')
                confidence = state.get('confidence_score', 0.0)

                logger.info(f"Final answer: {final_answer}\n\n---\n*Debug Info: Routed to {agent_type} agent (confidence: {confidence:.2f})*")
            
            return {
                **state,
                'final_answer': final_answer,
                'output': final_answer
            }
            
        except Exception as e:
            logger.error(f"❌ Error finalizing response: {str(e)}")
            
            fallback_response = "I apologize, but I encountered an error while preparing my response. Please try again."
            
            return {
                **state,
                'final_answer': fallback_response,
                'output': fallback_response
            }
    
    def controller(self, state: ManagerState) -> str:
        """
        Control the flow of execution in the graph
        """
        # Simple linear flow for now
        # Can be extended for more complex routing logic
        return 'route'
    
    def create_graph(self) -> StateGraph:
        """
        Create the execution graph for the Manager Agent
        """
        graph = StateGraph(ManagerState)
        
        # Add nodes
        graph.add_node('analyze', self.analyze_query)
        graph.add_node('delegate', self.route_to_agent)
        graph.add_node('finalize', self.finalize_response)
        
        # Set entry point
        graph.add_edge(START, 'analyze')
        
        # Add edges
        graph.add_edge('analyze', 'delegate')
        graph.add_edge('delegate', 'finalize')
        graph.add_edge('finalize', END)
        
        return graph.compile(debug=False)
    
    def invoke(self, input_data: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Main entry point for the Manager Agent
        
        Args:
            input_data: User query/input
            context: Additional context including cached plan options
            
        Returns:
            Dict containing the final response and metadata
        """
        start_time = time.time()
        
        if self.verbose:
            print(f'Entering ' + colored(self.name, 'black', 'on_white'))
            logger.info(f"📥 Processing input: {input_data}")
        
        # Extract user message
        if isinstance(input_data, dict):
            user_message = input_data.get('message', '') or input_data.get('input', '')
        else:
            user_message = input_data
        
        # Extract token
        token = input_data.get('token', '') if isinstance(input_data, dict) else ''
        if self.verbose:
            logger.info(f"🔑 ManagerAgent received token: {token[:10] if token else 'None'}...")
        
        # Save user message to chat history
        self.chat_history.add_user_message(user_message)
        
        # Initialize state
        state = {
            'input': user_message,
            'token': input_data.get('token', '') if isinstance(input_data, dict) else '',
            'messages': [],
            'route': '',
            'context': context or {},
            'reasoning_result': {},
            'agent_type': 'direct',
            'delegation_result': {},
            'final_answer': '',
            'output': '',
            'needs_planning': False,
            'needs_execution': False,
            'query_type': 'general',
            'confidence_score': 0.5
        }
        
        try:
            # Execute the graph
            result = self.graph.invoke(state)
            
            execution_time = time.time() - start_time
            
            # Save AI response to chat history
            ai_response = result.get('output', '')
            self.chat_history.add_ai_message(ai_response)
            
            if self.verbose:
                logger.info(f"✅ Request processed successfully in {execution_time:.2f}s")
                logger.info(f"💾 Saved conversation to history (session: {self.session_id})")
            
            # Prepare result with plan_options if available
            response = {
                'output': result.get('output', ''),
                'agent_type': result.get('agent_type', 'direct'),
                'confidence': result.get('confidence_score', 0.5),
                'execution_time': execution_time,
                'success': True
            }
            
            # Include plan_options from delegation_result if available
            delegation_result = result.get('delegation_result', {})
            if delegation_result.get('plan_options'):
                response['plan_options'] = delegation_result['plan_options']
                
            return response
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Error in Manager Agent execution: {str(e)}")
            
            # Save error response to chat history
            error_message = f'I apologize, but I encountered an error while processing your request: {str(e)}'
            self.chat_history.add_ai_message(error_message)
            
            return {
                'output': f'I apologize, but I encountered an error while processing your request: {str(e)}',
                'agent_type': 'error',
                'confidence': 0.0,
                'execution_time': execution_time,
                'success': False,
                'error': str(e)
            }
    
    def _get_device_list(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Call get_device_list tool directly from Manager
        Similar to PlanAgent's implementation but for Manager
        
        Args:
            token: Authentication token
            
        Returns:
            Device list data or None if failed
        """
        try:
            if self.verbose:
                logger.info(colored("📡 Manager calling get_device_list tool...", "cyan", attrs=['bold']))
            
            # Import MCP client
            from langchain_mcp_adapters.client import MultiServerMCPClient
            import asyncio
            
            async def async_get_device_list():
                """Async wrapper to call get_device_list"""
                mcp_client = None
                try:
                    # Initialize temporary MCP client
                    mcp_client = MultiServerMCPClient(
                        {"mcp-server": {"url": env.MCP_SERVER_URL, "transport": "sse"}}
                    )
                    await mcp_client.__aenter__()
                    
                    # Get tools
                    temp_tools = list(mcp_client.get_tools())
                    temp_tools_dict = {tool.name: tool for tool in temp_tools}
                    
                    if 'get_device_list' not in temp_tools_dict:
                        logger.warning("⚠️ get_device_list tool not available")
                        return None
                    
                    get_device_list_tool = temp_tools_dict['get_device_list']
                    
                    # Call tool with timeout
                    result = await asyncio.wait_for(
                        get_device_list_tool.ainvoke({"token": token}),
                        timeout=20.0
                    )
                    
                    if self.verbose:
                        logger.info(colored(f"✅ get_device_list returned successfully", "green", attrs=['bold']))
                    
                    # Parse JSON if result is string
                    if isinstance(result, str):
                        try:
                            result = json.loads(result)
                            if self.verbose:
                                logger.info(colored(f"✅ Parsed JSON response", "green"))
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ Failed to parse JSON response: {str(e)}")
                            return None
                    
                    return result
                    
                except asyncio.TimeoutError:
                    logger.warning("⚠️ get_device_list timeout after 20 seconds")
                    return None
                except Exception as e:
                    logger.error(f"❌ Error calling get_device_list: {str(e)}")
                    return None
                finally:
                    if mcp_client:
                        try:
                            await mcp_client.__aexit__(None, None, None)
                        except:
                            pass
            
            # Run async function
            try:
                loop = asyncio.get_running_loop()
                # We're in async context, need to run in executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(lambda: asyncio.run(async_get_device_list()))
                    result = future.result(timeout=25)
                    return result
            except RuntimeError:
                # No running loop, can run directly
                return asyncio.run(async_get_device_list())
            
        except Exception as e:
            logger.error(f"❌ Error in _get_device_list: {str(e)}")
            return None
    
    def stream(self, input_data: str):
        """
        Streaming interface (placeholder for future implementation)
        """
        # For now, just return the regular invoke result
        return self.invoke(input_data)
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get status of the Manager Agent and sub-agents
        """
        return {
            'manager_status': 'active',
            'sub_agents': {
                'plan_agent': self._plan_agent is not None,
                'tool_agent': self._tool_agent is not None
            },
            'cached_plans': len(self._cached_plan_options) > 0,
            'capabilities': get_agent_capabilities()
        }
    
    def clear_cache(self):
        """Clear cached plan options"""
        self._cached_plan_options = {}
        if self.verbose:
            logger.info("🗑️ Plan cache cleared")


# Export the ManagerAgent
__all__ = ["ManagerAgent"]