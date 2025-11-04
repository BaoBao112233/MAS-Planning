"""
Optimized Plan Agent for MAS-Planning system
Clear workflow (PlanAgent assumes analysis is provided by Manager):
1. Call get_device_list tool to get device information
2. Create 2 priority plans (Optimized, Conservative)
3. Execute selected plan with status updates
"""
from template.agent import BaseAgent
from template.agent.plan.state import PlanState
from template.agent.plan.prompts import (
    ANALYZE_INPUT_PROMPT, 
    CREATE_PLANS_PROMPT,
    UPDATE_PLAN_PROMPTS
)
from template.agent.plan.utils import extract_priority_plans
from template.agent.plan.parallel_executor import get_parallel_executor
from template.configs.environments import env
from template.message.message import HumanMessage, SystemMessage
from template.message.converter import convert_messages_list
from template.agent.plan.prompts import (
    ANALYZE_INPUT_PROMPT, 
    CREATE_PLANS_PROMPT,
    UPDATE_PLAN_PROMPTS
)
from template.agent.tool import ToolAgent
# from template.agent.api_client import APIClient
from template.configs.environments import env

from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph, END, START
from langchain_mcp_adapters.client import MultiServerMCPClient
from termcolor import colored
import time
import asyncio
import logging
import json
from typing import List, Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


class PlanAgent(BaseAgent):
    def __init__(self, 
                 model: str = "gemini-2.5-flash", 
                 temperature: float = 0.2, 
                 max_iteration=10, 
                 verbose=True):
        super().__init__()
        
        self.name = "Plan Agent"
        self.model = model
        self.temperature = temperature
        self.verbose = verbose
        self.tools = []
        self.tools_dict = {}
        self.mcp_client = None
        
        # Initialize LLM
        logger.info(colored(f"Plan Agent using model: {model}", "green", attrs=["bold"]))

        try:
            # Base LLM without tools (for plan generation)
            self.base_llm = ChatVertexAI(
                model_name=model,
                temperature=temperature,
                max_tokens=2048,  # Limit output to reduce latency
                project=env.GOOGLE_CLOUD_PROJECT,
                location=env.GOOGLE_CLOUD_LOCATION
            )
            
            # LLM with tools will be set in init_async()
            self.llm = self.base_llm
            
            logger.info(f"✅ LLM initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error initializing LLM: {str(e)}")
            self.llm = None
            self.base_llm = None

        self.max_iteration = max_iteration
        self.verbose = verbose
        # self.api_client = APIClient()
        self.tool_agent = None
        
        # Parallel execution optimizer
        self.parallel_executor = get_parallel_executor(verbose=self.verbose)
        self.use_parallel_execution = True  # Enable/disable parallel optimization
        
        # Initialize graph
        self.graph = self.create_graph()

        # Initialize MCP tools asynchronously
        try:
            import threading
            
            def run_init():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.init_async())
                    logger.info("📋 PlanAgent MCP tools initialized")
                except Exception as e:
                    logger.warning(colored(f"⚠️ PlanAgent MCP init failed: {e}", 'yellow'))
                finally:
                    loop.close()
            
            thread = threading.Thread(target=run_init)
            thread.start()
            thread.join(timeout=10)
            
            if thread.is_alive():
                logger.warning(colored("⚠️ PlanAgent MCP init timeout", 'yellow'))
                
        except Exception as e:
            logger.warning(colored(f"⚠️ Could not init PlanAgent MCP: {e}", 'yellow'))

    async def init_async(self):
        """Initialize MCP client and load tools"""
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            logger.warning("nest_asyncio not installed")
        
        try:
            self.mcp_client = MultiServerMCPClient(
                {"mcp-server": {"url": env.MCP_SERVER_URL, "transport": "sse"}}
            )
            await self.mcp_client.__aenter__()
            
            # Get tools
            self.tools = list(self.mcp_client.get_tools())
            self.tools_dict = {tool.name: tool for tool in self.tools}
            
            # Bind tools to LLM for tool-based workflows (NOT for plan generation)
            if self.tools:
                self.llm = self.base_llm.bind_tools(self.tools)
            else:
                self.llm = self.base_llm

            if self.verbose:
                logger.info(colored(f"🔧 Loaded {len(self.tools)} MCP tools", "green", attrs=["bold"]))
                
        except Exception as e:
            logger.error(f"❌ Error initializing MCP client: {str(e)}")
    
    def router(self, state: PlanState):
        """Route based on input and state"""
        selected_plan_id = state.get('selected_plan_id')
        
        # If plan already selected, execute it
        if selected_plan_id:
            return {**state, 'plan_type': 'execute'}
        
        # Check if message indicates plan selection
        input_msg = state.get('input', '').strip().lower()
        selection_keywords = ['plan 1', 'plan 2', '1', '2', 
                             'plan a', 'plan b', 'a', 'b',
                             'optimized', 'conservative']
        
        if any(keyword == input_msg for keyword in selection_keywords):
            # Map selection to plan ID
            if input_msg in ['plan 1', '1', 'plan a', 'a', 'optimized']:
                selected_plan_id = 1
            elif input_msg in ['plan 2', '2', 'plan b', 'b', 'conservative']:
                selected_plan_id = 2
            
            return {**state, 'plan_type': 'execute', 'selected_plan_id': selected_plan_id}
        
        # Default: Create new plans
        return {**state, 'plan_type': 'create_plans'}

    def create_plans(self, state: PlanState):
        """
        Main workflow (expects input analysis to be provided by Manager):
        1. Call get_device_list to get device information
        2. Create 2 priority plans
        """
        user_input = state.get('input', '')
        token = state.get('token', '')

        # Debug: Check what's in state
        if self.verbose:
            logger.info(f"🔍 DEBUG - State keys: {list(state.keys())}")
            logger.info(f"🔍 DEBUG - input_analysis in state: {'input_analysis' in state}")
            logger.info(f"🔍 DEBUG - input_analysis value: {state.get('input_analysis')}")

        # Manager is expected to perform the analysis and populate 'input_analysis'
        input_analysis = state.get('input_analysis') or state.get('reasoning_result')

        if not input_analysis:
            # Graceful fallback: analyze locally if Manager didn't provide analysis
            logger.warning(colored("⚠️ No input analysis provided by Manager; performing local analysis as fallback", 'yellow'))
            input_analysis = self._analyze_user_input(user_input)
        else:
            if self.verbose:
                logger.info(colored("✅ Using Manager's analysis (no duplicate LLM call)", "green", attrs=["bold"]))
                logger.info(f"📊 Analysis received: {input_analysis.get('reasoning', 'N/A')[:100]}...")

        if self.verbose:
            logger.info(colored("\n" + "="*80, "cyan"))
            logger.info(colored("🎯 STEP 1: RETRIEVING DEVICE INFORMATION", "cyan", attrs=["bold"]))
            logger.info(colored("="*80, "cyan"))
            logger.info(f"📝 Input (summary): {input_analysis.get('primary_intent', user_input)}")

        # Step 1 (PlanAgent): Get device information
        device_info = None
        if token:
            device_info = self._get_device_list(token)
            if device_info and self.verbose:
                room_count = self._count_rooms(device_info)
                logger.info(colored(f"✅ Device information retrieved successfully", "green"))
                logger.info(f"🏠 Found {room_count} rooms with devices")
        else:
            logger.warning(colored("⚠️ No token provided - cannot retrieve devices", "yellow"))

        # Step 2: Create 2 priority plans
        if self.verbose:
            logger.info(colored("\n" + "="*80, "cyan"))
            logger.info(colored("🎯 STEP 2: CREATING 2 PRIORITY PLANS", "cyan", attrs=["bold"]))
            logger.info(colored("="*80, "cyan"))

        plan_options = self._create_priority_plans(user_input, input_analysis, device_info)
        
        if self.verbose:
            logger.info(colored("✅ Plans created successfully", "green", attrs=["bold"]))
            logger.info(f"🥇 Optimized Plan: {len(plan_options.get('optimized_plan', []))} tasks")
            logger.info(f"🥈 Conservative Plan: {len(plan_options.get('conservative_plan', []))} tasks")
            logger.info(colored("="*80 + "\n", "cyan"))
        
        # Format plans for output
        # plans_text = self._format_plans_for_output(plan_options)
        
        return {
            **state, 
            'plan_options': plan_options, 
            'needs_user_selection': True,
            'device_context': device_info
        }

    def _analyze_user_input(self, user_input: str) -> dict:
        """Analyze user input to extract intent and requirements"""
        try:
            prompt = ANALYZE_INPUT_PROMPT.format(user_input=user_input)
            
            messages = convert_messages_list([
                SystemMessage("You are an expert at analyzing smart home requests. Always respond with valid JSON."),
                HumanMessage(prompt)
            ])
            
            response = self.llm.invoke(messages)
            
            # Try to parse JSON from response
            content = response.content.strip()
            
            # Extract JSON if wrapped in markdown code blocks
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            try:
                analysis = json.loads(content)
            except json.JSONDecodeError:
                # Fallback: Try to find JSON-like structure
                import re
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group(0))
                else:
                    raise ValueError("Could not parse JSON")
            
            return analysis
            
        except Exception as e:
            logger.warning(f"⚠️ Error analyzing input: {str(e)}, using fallback")
            # Fallback analysis
            return {
                "primary_intent": user_input,
                "key_requirements": [user_input],
                "context": {
                    "time_of_day": "unknown",
                    "situation": "general",
                    "urgency": "normal"
                },
                "scope": {
                    "rooms": ["all"],
                    "device_types": ["all"],
                    "all_house": True
                },
                "priority_hints": {
                    "security": 33,
                    "convenience": 33,
                    "energy": 34
                }
            }

    def _get_device_list(self, token: str) -> dict:
        """Call get_device_list tool to retrieve device information"""
        try:
            logger.info(colored("📡 Calling get_device_list tool...", "green", attrs=['bold']))
            
            # Create fresh MCP client for this call (like ToolAgent does)
            import concurrent.futures
            
            def run_tool_call():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Create fresh client
                    temp_client = MultiServerMCPClient(
                        {"mcp-server": {"url": env.MCP_SERVER_URL, "transport": "sse"}}
                    )
                    loop.run_until_complete(temp_client.__aenter__())
                    
                    # Get tools
                    temp_tools = list(temp_client.get_tools())
                    temp_tools_dict = {t.name: t for t in temp_tools}
                    
                    if 'get_device_list' not in temp_tools_dict:
                        logger.warning("⚠️ get_device_list tool not available in fresh client")
                        return None
                    
                    get_device_list_tool = temp_tools_dict['get_device_list']
                    
                    # Call tool
                    result = loop.run_until_complete(
                        asyncio.wait_for(
                            get_device_list_tool.ainvoke({"token": token}),
                            timeout=15.0
                        )
                    )
                    
                    return result
                    
                finally:
                    # Cleanup
                    if 'temp_client' in locals():
                        try:
                            loop.run_until_complete(temp_client.__aexit__(None, None, None))
                        except:
                            pass
                    loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_tool_call)
                result = future.result(timeout=20)
            
            if self.verbose and result:
                logger.info(f"📱 Device data retrieved: {len(str(result))} characters")
            
            return result
            
        except concurrent.futures.TimeoutError:
            logger.warning("⚠️ get_device_list timeout after 20 seconds")
            return None
        except Exception as e:
            logger.error(f"❌ Error calling get_device_list: {str(e)}")
            return None

    def _create_priority_plans(self, user_input: str, input_analysis: dict, device_info) -> dict:
        """Create 2 priority plans based on analysis and device info"""
        
        # Extract room scope from analysis
        mentioned_rooms = input_analysis.get('scope', {}).get('rooms', [])
        all_house = input_analysis.get('scope', {}).get('all_house', False)
        
        # Format device context (filtered by room if specified)
        device_context = self._format_device_context(
            device_info, 
            filter_rooms=mentioned_rooms if (mentioned_rooms and not all_house) else None
        ) if device_info else "No device information available."
        
        # Format input analysis
        analysis_text = self._format_input_analysis(input_analysis)
        
        # Build prompt
        prompt = CREATE_PLANS_PROMPT.format(
            input_analysis=analysis_text,
            device_context=device_context
        )
        
        messages = convert_messages_list([
            SystemMessage("You are an expert smart home planner. Always create exactly 2 plans in the specified XML format. ONLY control devices in rooms explicitly mentioned in the user request."),
            HumanMessage(prompt)
        ])
        
        if self.verbose:
            logger.info(colored("🤖 Generating plans with LLM...", "cyan"))
            logger.info(f"📏 Prompt length: {len(prompt)} characters")
        
        try:
            # Use base_llm WITHOUT tools to avoid tool call responses
            llm_to_use = self.base_llm if hasattr(self, 'base_llm') and self.base_llm else self.llm
            llm_response = llm_to_use.invoke(messages)
            
            if self.verbose:
                logger.info(f"✅ LLM response received: {len(llm_response.content)} characters")
                if len(llm_response.content) == 0:
                    logger.warning(f"⚠️ Empty LLM response! Response object: {llm_response}")
                    logger.warning(f"⚠️ Prompt preview: {prompt[:500]}...")
                else:
                    logger.info(f"📝 Response preview: {llm_response.content[:200]}...")
            
            # Extract plans from XML format
            plan_data = extract_priority_plans(llm_response.content)
            
            # Validate plans
            if not any(plan_data.get(key) for key in ['Optimized_Plan', 'Conservative_Plan']):
                logger.warning(colored("⚠️ No valid plans extracted, using fallback", 'yellow'))
                plan_data = self._get_fallback_plans()
            
            return {
                'optimized_plan': plan_data.get('Optimized_Plan', []),
                'conservative_plan': plan_data.get('Conservative_Plan', [])
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating plans: {str(e)}")
            return self._get_fallback_plans()

    def _format_input_analysis(self, analysis: dict) -> str:
        """Format input analysis for prompt"""
        rooms = analysis.get('scope', {}).get('rooms', [])
        all_house = analysis.get('scope', {}).get('all_house', False)
        
        # Build room scope emphasis
        if all_house:
            room_scope = "**ALL ROOMS** (whole house automation)"
        elif rooms and len(rooms) > 0:
            room_scope = f"**ONLY: {', '.join(rooms).upper()}** (do NOT control devices in other rooms)"
        else:
            room_scope = "Not specified (infer from context)"
        
        return f"""
**User Request Analysis:**
- Primary Intent: {analysis.get('primary_intent', 'Unknown')}
- Key Requirements: {', '.join(analysis.get('key_requirements', []))}
- Context: 
  - Time: {analysis.get('context', {}).get('time_of_day', 'Unknown')}
  - Situation: {analysis.get('context', {}).get('situation', 'General')}
  - Urgency: {analysis.get('context', {}).get('urgency', 'Normal')}
- **ROOM SCOPE (CRITICAL)**: {room_scope}
- Device Types: {', '.join(analysis.get('scope', {}).get('device_types', ['all']))}
- Priority Hints:
  - Security: {analysis.get('priority_hints', {}).get('security', 33)}%
  - Convenience: {analysis.get('priority_hints', {}).get('convenience', 33)}%
  - Energy: {analysis.get('priority_hints', {}).get('energy', 34)}%
"""

    def _format_device_context(self, device_context, filter_rooms=None) -> str:
        """
        Format device context for prompt - optimized for brevity
        
        Args:
            device_context: Raw device data
            filter_rooms: List of room names to include (None = all rooms)
        """
        if not device_context:
            return "No device information available."
        
        try:
            if isinstance(device_context, str):
                device_context = json.loads(device_context)
            
            formatted = ""
            
            if isinstance(device_context, list):
                for room in device_context:
                    room_name = room.get('room_name', 'Unknown')
                    
                    # Filter by room if specified
                    if filter_rooms:
                        # Flexible room matching:
                        # - Case-insensitive
                        # - Remove spaces for comparison (bedroom = bed room)
                        # - Partial match (bedroom matches "Bed room 1")
                        room_name_normalized = room_name.lower().replace(' ', '')
                        matched = False
                        
                        for filter_room in filter_rooms:
                            filter_normalized = filter_room.lower().replace(' ', '')
                            # Match if either contains the other
                            if filter_normalized in room_name_normalized or room_name_normalized in filter_normalized:
                                matched = True
                                break
                        
                        if not matched:
                            continue  # Skip this room
                    
                    formatted += f"**{room_name}**: "
                    
                    # Collect device names only (skip long descriptions)
                    items = []
                    for device in room.get('devices', []):
                        name = device.get('name') or ''
                        name = name.split(',')[0] if name else 'Unknown Device'
                        status = device.get('device_status', '')
                        items.append(f"{name} ({status})" if status else name)
                    
                    for button in room.get('buttons', []):
                        name = button.get('name') or ''
                        name = name.split(',')[0] if name else 'Unknown Button'
                        items.append(name)
                    
                    formatted += ", ".join(items) + "\n"
                
                if not formatted.strip():
                    return f"No devices found in specified rooms: {', '.join(filter_rooms)}" if filter_rooms else "No devices available."
                    
            else:
                formatted = str(device_context)[:500] + "..."
            
            return formatted
            
        except Exception as e:
            logger.warning(f"⚠️ Error formatting device context: {str(e)}")
            return f"Device context: {str(device_context)[:300]}..."

    def _count_rooms(self, device_info) -> int:
        """Count number of rooms"""
        try:
            if isinstance(device_info, str):
                device_info = json.loads(device_info)
            if isinstance(device_info, list):
                return len(device_info)
            return 0
        except:
            return 0

    def _get_fallback_plans(self) -> dict:
        """Generate fallback plans when LLM fails"""
        return {
            'optimized_plan': [
                'Lock all smart door locks and verify status',
                'Set living room AC to comfortable 24°C',
                'Turn on all essential interior lights',
                'Enable motion sensors in all entry areas'
            ],
            'conservative_plan': [
                'Lock all smart door locks and verify status',
                'Turn off all lights in unoccupied rooms',
                'Set AC to energy-saving 26°C',
                'Enable eco-mode for all compatible devices'
            ]
        }

    # def _format_plans_for_output(self, plan_options: dict) -> str:
    #     """Format the 3 plans for user display"""
    #     output = "🏠 **Smart Home Automation Plans**\n\n"
    #     output += "Here are 3 priority plans based on your request:\n\n"
        
    #     plan_names = [
    #         ("🔒 Security Priority Plan", 'security_plan'),
    #         ("🏠 Convenience Priority Plan", 'convenience_plan'), 
    #         ("🌱 Energy Efficiency Priority Plan", 'energy_plan')
    #     ]
        
    #     for i, (name, key) in enumerate(plan_names, 1):
    #         output += f"**{i}. {name}**\n"
    #         tasks = plan_options.get(key, [])
    #         if tasks:
    #             for task in tasks:
    #                 output += f"• {task}\n"
    #         else:
    #             output += "• No tasks available\n"
    #         output += "\n"
        
    #     output += "💬 **How to choose:**\n"
    #     output += "Reply with \"1\", \"2\", or \"3\" to select a plan and start execution.\n"
    #     output += "Or describe any modifications you'd like to make.\n\n"
    #     output += "🤖 What would you like to do?"
        
    #     return output

    def init_sub_agents(self):
        """Initialize ToolAgent when needed"""
        if self.tool_agent is None:
            self.tool_agent = ToolAgent(
                model=self.model,
                temperature=self.temperature,
                verbose=self.verbose
            )
            # Initialize ToolAgent async
            try:
                import threading
                
                def run_async_init():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self.tool_agent.init_async())
                    finally:
                        loop.close()
                
                thread = threading.Thread(target=run_async_init)
                thread.start()
                thread.join(timeout=10)
                
                if thread.is_alive():
                    logger.warning(colored("⚠️ ToolAgent async init timeout", 'yellow'))
                    
            except Exception as e:
                logger.warning(colored(f"⚠️ Could not init ToolAgent async: {e}", 'yellow'))

    def execute_selected_plan(self, state: PlanState):
        """
        Execute selected plan with OPTIMIZED PARALLEL execution
        Uses async parallel executor for 40-50% performance improvement
        """
        selected_plan_id = state.get('selected_plan_id')
        plan_options = state.get('plan_options', {})
        
        if not selected_plan_id:
            return {**state, 'output': 'No plan selected'}
        
        if not plan_options:
            return {**state, 'output': 'No plan options available'}
        
        # Select plan
        plan_mapping = {
            1: ('optimized_plan', 'Optimized Plan (Security + Convenience)'),
            2: ('conservative_plan', 'Conservative Plan (Energy + Security)')
        }
        
        if selected_plan_id not in plan_mapping:
            return {**state, 'output': 'Invalid plan selection'}
        
        plan_key, plan_type = plan_mapping[selected_plan_id]
        selected_plan = plan_options[plan_key]
        
        if self.verbose:
            logger.info(colored(f'\n✅ Selected Plan: {plan_type}', "green", attrs=["bold"]))
            logger.info('📋 Tasks:')
            for i, task in enumerate(selected_plan, 1):
                logger.info(f'   {i}. {task}')
        
        # Initialize sub-agents
        self.init_sub_agents()
        
        # ========================================
        # PARALLEL EXECUTION OPTIMIZATION
        # Use async parallel executor if enabled
        # ========================================
        if self.use_parallel_execution:
            try:
                # Run parallel execution in new event loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results = loop.run_until_complete(
                        self._execute_plan_async_parallel(selected_plan, state.get('token', ''))
                    )
                    
                    # Convert results to expected format
                    execution_results = [
                        {
                            "task_number": r.task_number,
                            "task": r.task,
                            "tool_execution": r.result.get('output', '') if isinstance(r.result, dict) else str(r.result),
                            "status": r.status
                        }
                        for r in results
                    ]
                    
                    # Build output
                    completed = sum(1 for r in results if r.status == 'completed')
                    failed = sum(1 for r in results if r.status == 'failed')
                    
                    output = f"""🎯 **{plan_type} Execution Complete**

✅ Tasks completed: {completed}/{len(selected_plan)}
{"❌ Tasks failed: " + str(failed) if failed > 0 else ""}

**Execution Summary:**
"""
                    for result in execution_results:
                        status_icon = "✅" if result['status'] == 'completed' else "❌"
                        output += f"\n{status_icon} Task {result['task_number']}: {result['task']}"
                        if result['status'] == 'completed':
                            output += f"\n   → {result['tool_execution'][:100]}..."
                    
                    return {
                        **state,
                        'execution_results': execution_results,
                        'output': output,
                        'plan_type': plan_type,
                        'completed_tasks': completed,
                        'failed_tasks': failed
                    }
                    
                finally:
                    loop.close()
                    
            except Exception as e:
                logger.error(f"❌ Parallel execution failed: {e}")
                logger.info("⚠️ Falling back to sequential execution")
                # Fall through to original implementation
        
        # ========================================
        # ORIGINAL SEQUENTIAL/THREAD-POOL EXECUTION
        # Fallback when parallel is disabled or fails
        # ========================================
        
        # Prepare for parallel execution
        import concurrent.futures
        import threading
        
        # Thread-safe data structures
        execution_results = []
        completed_tasks = []
        failed_tasks = []
        results_lock = threading.Lock()
        
        def execute_single_task(task_info):
            """Execute a single task in a separate thread"""
            task_number, task = task_info
            token = state.get('token', '')
            
            try:
                # Log task start (thread-safe)
                logger.info(colored(f"\n🚀 [Thread-{threading.current_thread().name}] Executing Task {task_number}/{len(selected_plan)}: {task}", "cyan", attrs=["bold"]))
                
                # if self.api_client:
                #     with results_lock:
                #         self.api_client.update_task_status(task, "in_progress")
                
                # Create new event loop for this thread
                def call_tool_agent(input_data):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.tool_agent.ainvoke(input_data))
                    finally:
                        loop.close()
                
                # Execute tool agent
                tool_result = call_tool_agent({"input": task, "token": token})
                
                tool_output = tool_result.get('output', '')
                has_error = tool_result.get('error', '')
                
                # Thread-safe result collection
                with results_lock:
                    if tool_output and not has_error:
                        execution_results.append({
                            "task_number": task_number,
                            "task": task,
                            "tool_execution": tool_output,
                            "status": "completed"
                        })
                        completed_tasks.append(task)
                        
                        # if self.api_client:
                        #     self.api_client.update_task_status(task, "completed", tool_output)
                        
                        logger.info(colored(f"✅ [Thread-{threading.current_thread().name}] Task {task_number} completed", "green"))
                        return ("success", task_number, task, tool_output)
                    else:
                        error_msg = has_error or 'Unknown error'
                        execution_results.append({
                            "task_number": task_number,
                            "task": task,
                            "tool_execution": error_msg,
                            "status": "failed"
                        })
                        failed_tasks.append(task)
                        
                        # if self.api_client:
                        #     self.api_client.update_task_status(task, "failed", error_msg)
                        
                        logger.error(colored(f"❌ [Thread-{threading.current_thread().name}] Task {task_number} failed: {error_msg}", "red"))
                        return ("failed", task_number, task, error_msg)
                        
            except Exception as e:
                error_msg = f"Task execution error: {str(e)}"
                
                with results_lock:
                    execution_results.append({
                        "task_number": task_number,
                        "task": task,
                        "tool_execution": error_msg,
                        "status": "failed"
                    })
                    failed_tasks.append(task)
                    
                    # if self.api_client:
                    #     self.api_client.update_task_status(task, "failed", error_msg)
                    
                    logger.error(colored(f"❌ [Thread-{threading.current_thread().name}] Task {task_number} exception: {str(e)}", "red"))
                    return ("error", task_number, task, error_msg)
        
        # Execute all tasks in parallel
        try:
            num_tasks = len(selected_plan)
            logger.info(colored(f"\n🔥 Starting PARALLEL execution with {num_tasks} threads", "magenta", attrs=["bold"]))
            
            # Create ThreadPoolExecutor with number of workers = number of tasks
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_tasks) as executor:
                # Prepare task info: (task_number, task)
                tasks_with_numbers = [(i+1, task) for i, task in enumerate(selected_plan)]
                
                # Submit all tasks to executor
                futures = {
                    executor.submit(execute_single_task, task_info): task_info 
                    for task_info in tasks_with_numbers
                }
                
                # Wait for all tasks to complete with timeout
                completed_futures = concurrent.futures.wait(
                    futures, 
                    timeout=60,  # 60 seconds total timeout for all tasks
                    return_when=concurrent.futures.ALL_COMPLETED
                )
                
                # Handle timed out tasks
                if completed_futures.not_done:
                    logger.warning(colored(f"⚠️ {len(completed_futures.not_done)} tasks timed out", "yellow"))
                    for future in completed_futures.not_done:
                        task_info = futures[future]
                        task_number, task = task_info
                        
                        with results_lock:
                            execution_results.append({
                                "task_number": task_number,
                                "task": task,
                                "tool_execution": "Task execution timed out after 60 seconds",
                                "status": "failed"
                            })
                            failed_tasks.append(task)
                            
                            # if self.api_client:
                            #     self.api_client.update_task_status(task, "failed", "Timeout")
                
                logger.info(colored(f"\n✨ All tasks completed/timed out", "magenta", attrs=["bold"]))
                
        except Exception as e:
            logger.error(colored(f"❌ Critical error in parallel execution: {str(e)}", "red", attrs=["bold"]))
        
        # Finalize
        total_tasks = len(selected_plan)
        completed_count = len(completed_tasks)
        failed_count = len(failed_tasks)
        success_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0
        
        # if self.api_client:
        #     final_status = "completed"
        #     final_summary = f"Completed {completed_count}/{total_tasks} tasks ({success_rate:.1f}%)"
        #     self.api_client.update_plan_status(final_status, final_summary)
        
        # Generate output
        output = f"🎯 **{plan_type} Execution Complete**\n\n"
        output += f"📋 **Summary:**\n"
        output += f"• Total Tasks: {total_tasks}\n"
        output += f"• Completed: {completed_count}\n" 
        output += f"• Failed: {failed_count}\n"
        output += f"• Success Rate: {success_rate:.1f}%\n\n"
        
        if completed_tasks:
            output += f"✅ **Completed Tasks:**\n"
            for task in completed_tasks:
                output += f"• {task}\n"
            output += "\n"
        
        if failed_tasks:
            output += f"❌ **Failed Tasks:**\n"
            for task in failed_tasks:
                output += f"• {task}\n"
        
        return {
            **state, 
            'plan': selected_plan, 
            'output': output, 
            'execution_results': execution_results
        }
    
    # ========================================
    # ASYNC PARALLEL EXECUTION OPTIMIZATION
    # ========================================
    
    async def _execute_plan_async_parallel(self, tasks: List[str], token: str):
        """
        Execute plan tasks using async parallel executor
        Performance: 40-50% faster than sequential execution
        """
        if self.verbose:
            logger.info(colored("\n⚡ ASYNC PARALLEL EXECUTION MODE", "magenta", attrs=["bold"]))
        
        # Define task executor function
        async def execute_task(task: str, task_num: int, token: str) -> Dict:
            """Execute single task via Tool Agent"""
            try:
                # Tool Agent already supports async
                result = await self.tool_agent.ainvoke({
                    "input": task,
                    "token": token
                })
                
                return {
                    'output': result.get('output', ''),
                    'status': 'completed' if result.get('output') else 'failed',
                    'error': result.get('error', '')
                }
                
            except Exception as e:
                logger.error(f"❌ Task {task_num} error: {e}")
                return {
                    'output': '',
                    'status': 'failed',
                    'error': str(e)
                }
        
        # Execute with parallel executor
        results = await self.parallel_executor.execute_plan_parallel(
            tasks=tasks,
            executor_func=execute_task,
            token=token,
            max_parallel=5  # Max 5 concurrent tasks
        )
        
        return results

    def route_controller(self, state: PlanState):
        """Control routing logic"""
        plan_type = state.get('plan_type')
        if plan_type == 'execute':
            return 'execute_selected'
        elif plan_type == 'create_plans':
            return 'create_plans'
        elif state.get('needs_user_selection', False):
            return 'wait_selection'
        return plan_type

    def create_graph(self):
        """Create LangGraph workflow"""
        graph = StateGraph(PlanState)
        
        graph.add_node('route', self.router)
        graph.add_node('create_plans', self.create_plans)
        graph.add_node('execute_selected', self.execute_selected_plan)
        graph.add_node('wait_selection', lambda state: {
            **state, 
            'output': 'waiting_for_selection'
        })

        graph.add_edge(START, 'route')
        graph.add_conditional_edges('route', self.route_controller)
        graph.add_conditional_edges(
            'create_plans', 
            lambda state: 'wait_selection' if state.get('needs_user_selection') else 'execute_selected'
        )
        graph.add_edge('execute_selected', END)
        graph.add_edge('wait_selection', END)

        return graph.compile(debug=False)

    def invoke(self, input: str, selected_plan_id: int = None, plan_options: dict = None, token: str = None, input_analysis: dict = None):
        """Main entry point"""
        self.start_time = time.time()
        
        if self.verbose:
            print(f'Entering ' + colored(self.name, 'black', 'on_white'))
        
        state = {
            'input': input,
            'plan_status': '',
            'route': '',
            'plan': [],
            'plan_options': plan_options or {},
            'input_analysis': input_analysis,
            'needs_user_selection': False,
            'selected_plan_id': selected_plan_id,
            'token': token,
            'output': ''
        }
        
        agent_response = self.graph.invoke(state)
        return agent_response

    def stream(self, input: str):
        pass