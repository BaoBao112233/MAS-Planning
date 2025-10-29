"""
Optimized Plan Agent for MAS-Planning system
Clear workflow:
1. Analyze user input
2. Call get_device_list tool to get device information
3. Create 3 priority plans (Security, Convenience, Energy)
4. Execute selected plan with status updates
"""
from template.agent import BaseAgent
from template.agent.plan.state import PlanState
from template.message.message import SystemMessage, HumanMessage
from template.message.converter import convert_messages_list
from template.agent.plan.utils import extract_priority_plans
from template.agent.plan.prompts import (
    ANALYZE_INPUT_PROMPT, 
    CREATE_PLANS_PROMPT,
    UPDATE_PLAN_PROMPTS
)
from template.agent.meta import MetaAgent
from template.agent.tool import ToolAgent
from template.agent.api_client import APIClient
from template.configs.environments import env

from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph, END, START
from langchain_mcp_adapters.client import MultiServerMCPClient
from termcolor import colored
import time
import asyncio
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


class PlanAgent(BaseAgent):
    def __init__(self, 
                 model: str = "gemini-2.5-pro", 
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
        try:
            self.llm = ChatVertexAI(
                model_name=model,
                temperature=temperature,
                project=env.GOOGLE_CLOUD_PROJECT,
                location=env.GOOGLE_CLOUD_LOCATION
            )
            logger.info(f"✅ LLM initialized successfully")
        except Exception as e:
            logger.error(f"❌ Error initializing LLM: {str(e)}")
            self.llm = None

        self.max_iteration = max_iteration
        self.verbose = verbose
        self.api_client = APIClient()
        self.meta_agent = None
        self.tool_agent = None
        
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
            
            # Bind tools to LLM
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
        selection_keywords = ['plan 1', 'plan 2', 'plan 3', '1', '2', '3', 
                             'plan a', 'plan b', 'plan c', 'a', 'b', 'c']
        
        if any(keyword == input_msg for keyword in selection_keywords):
            # Map selection to plan ID
            if input_msg in ['plan 1', '1', 'plan a', 'a']:
                selected_plan_id = 1
            elif input_msg in ['plan 2', '2', 'plan b', 'b']:
                selected_plan_id = 2
            elif input_msg in ['plan 3', '3', 'plan c', 'c']:
                selected_plan_id = 3
            
            return {**state, 'plan_type': 'execute', 'selected_plan_id': selected_plan_id}
        
        # Default: Create new plans
        return {**state, 'plan_type': 'create_plans'}

    def create_plans(self, state: PlanState):
        """
        Main workflow:
        1. Analyze user input
        2. Call get_device_list to get device information
        3. Create 3 priority plans
        """
        user_input = state.get('input', '')
        token = state.get('token', '')
        
        if self.verbose:
            logger.info(colored("\n" + "="*80, "cyan"))
            logger.info(colored("🎯 STEP 1: ANALYZING USER INPUT", "cyan", attrs=["bold"]))
            logger.info(colored("="*80, "cyan"))
            logger.info(f"📝 Input: {user_input}")
        
        # Step 1: Analyze user input
        input_analysis = self._analyze_user_input(user_input)
        
        if self.verbose:
            logger.info(colored("✅ Input analysis complete", "green"))
            logger.info(f"📊 Primary Intent: {input_analysis.get('primary_intent', 'Unknown')}")
            logger.info(f"📊 Key Requirements: {', '.join(input_analysis.get('key_requirements', []))}")
        
        # Step 2: Get device information
        device_info = None
        if token:
            if self.verbose:
                logger.info(colored("\n" + "="*80, "cyan"))
                logger.info(colored("🎯 STEP 2: RETRIEVING DEVICE INFORMATION", "cyan", attrs=["bold"]))
                logger.info(colored("="*80, "cyan"))
            
            device_info = self._get_device_list(token)
            
            if device_info:
                if self.verbose:
                    room_count = self._count_rooms(device_info)
                    logger.info(colored(f"✅ Device information retrieved successfully", "green"))
                    logger.info(f"🏠 Found {room_count} rooms with devices")
            else:
                logger.warning(colored("⚠️ No device information received", "yellow"))
        else:
            logger.warning(colored("⚠️ No token provided - cannot retrieve devices", "yellow"))
        
        # Step 3: Create 3 priority plans
        if self.verbose:
            logger.info(colored("\n" + "="*80, "cyan"))
            logger.info(colored("🎯 STEP 3: CREATING 3 PRIORITY PLANS", "cyan", attrs=["bold"]))
            logger.info(colored("="*80, "cyan"))
        
        plan_options = self._create_priority_plans(user_input, input_analysis, device_info)
        
        if self.verbose:
            logger.info(colored("✅ Plans created successfully", "green", attrs=["bold"]))
            logger.info(f"🔒 Security Plan: {len(plan_options.get('security_plan', []))} tasks")
            logger.info(f"🏠 Convenience Plan: {len(plan_options.get('convenience_plan', []))} tasks")
            logger.info(f"🌱 Energy Plan: {len(plan_options.get('energy_plan', []))} tasks")
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
        """Create 3 priority plans based on analysis and device info"""
        
        # Format device context
        device_context = self._format_device_context(device_info) if device_info else "No device information available."
        
        # Format input analysis
        analysis_text = self._format_input_analysis(input_analysis)
        
        # Build prompt
        prompt = CREATE_PLANS_PROMPT.format(
            input_analysis=analysis_text,
            device_context=device_context
        )
        
        messages = convert_messages_list([
            SystemMessage("You are an expert smart home planner. Always create exactly 3 plans in the specified XML format."),
            HumanMessage(prompt)
        ])
        
        if self.verbose:
            logger.info(colored("🤖 Generating plans with LLM...", "cyan"))
        
        try:
            llm_response = self.llm.invoke(messages)
            
            if self.verbose:
                logger.info(f"✅ LLM response received: {len(llm_response.content)} characters")
            
            # Extract plans from XML format
            plan_data = extract_priority_plans(llm_response.content)
            
            # Validate plans
            if not any(plan_data.get(key) for key in ['Security_Plan', 'Convenience_Plan', 'Energy_Plan']):
                logger.warning(colored("⚠️ No valid plans extracted, using fallback", 'yellow'))
                plan_data = self._get_fallback_plans()
            
            return {
                'security_plan': plan_data.get('Security_Plan', []),
                'convenience_plan': plan_data.get('Convenience_Plan', []),
                'energy_plan': plan_data.get('Energy_Plan', [])
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating plans: {str(e)}")
            return self._get_fallback_plans()

    def _format_input_analysis(self, analysis: dict) -> str:
        """Format input analysis for prompt"""
        return f"""
**User Request Analysis:**
- Primary Intent: {analysis.get('primary_intent', 'Unknown')}
- Key Requirements: {', '.join(analysis.get('key_requirements', []))}
- Context: 
  - Time: {analysis.get('context', {}).get('time_of_day', 'Unknown')}
  - Situation: {analysis.get('context', {}).get('situation', 'General')}
  - Urgency: {analysis.get('context', {}).get('urgency', 'Normal')}
- Scope:
  - Rooms: {', '.join(analysis.get('scope', {}).get('rooms', ['all']))}
  - Device Types: {', '.join(analysis.get('scope', {}).get('device_types', ['all']))}
  - Whole House: {'Yes' if analysis.get('scope', {}).get('all_house', False) else 'No'}
- Priority Hints:
  - Security: {analysis.get('priority_hints', {}).get('security', 33)}%
  - Convenience: {analysis.get('priority_hints', {}).get('convenience', 33)}%
  - Energy: {analysis.get('priority_hints', {}).get('energy', 34)}%
"""

    def _format_device_context(self, device_context) -> str:
        """Format device context for prompt"""
        if not device_context:
            return "No device information available."
        
        try:
            if isinstance(device_context, str):
                device_context = json.loads(device_context)
            
            formatted = "📱 **AVAILABLE DEVICES IN YOUR HOME:**\n\n"
            
            if isinstance(device_context, list):
                for room in device_context:
                    room_name = room.get('room_name', 'Unknown Room')
                    formatted += f"🏠 **{room_name}**\n"
                    
                    devices = room.get('devices', [])
                    for device in devices:
                        device_name = device.get('name', 'Unknown')
                        device_type = device.get('device_type', 'Unknown')
                        status = device.get('device_status', 'Unknown')
                        formatted += f"  • {device_name} ({device_type}) - Status: {status}\n"
                    
                    buttons = room.get('buttons', [])
                    for button in buttons:
                        button_name = button.get('name', 'Unknown')
                        button_type = button.get('button_type', 'Unknown')
                        formatted += f"  • {button_name} ({button_type})\n"
                    
                    formatted += "\n"
            else:
                formatted += json.dumps(device_context, indent=2)
            
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
            'security_plan': [
                'Lock all smart door locks and verify status',
                'Turn on all exterior lights for security',
                'Enable motion sensors in all entry areas',
                'Activate security camera monitoring'
            ],
            'convenience_plan': [
                'Set living room AC to comfortable 24°C',
                'Turn on bedroom lights at 30% brightness',
                'Create cozy lighting in main areas',
                'Adjust temperature for optimal comfort'
            ],
            'energy_plan': [
                'Turn off all lights in unoccupied rooms',
                'Set AC to energy-saving 26°C',
                'Disable unused appliances and devices',
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
        """Initialize MetaAgent and ToolAgent when needed"""
        if self.meta_agent is None:
            self.meta_agent = MetaAgent(
                model=self.model,
                temperature=self.temperature,
                verbose=self.verbose
            )
        
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
        """Execute selected plan with status updates"""
        selected_plan_id = state.get('selected_plan_id')
        plan_options = state.get('plan_options', {})
        
        if not selected_plan_id:
            return {**state, 'output': 'No plan selected'}
        
        if not plan_options:
            return {**state, 'output': 'No plan options available'}
        
        # Select plan
        plan_mapping = {
            1: ('security_plan', 'Security Priority Plan'),
            2: ('convenience_plan', 'Convenience Priority Plan'),
            3: ('energy_plan', 'Energy Efficiency Priority Plan')
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
        
        # Upload plan to API
        if self.api_client:
            plan_data = {
                "input": state.get('input', ''),
                "plan_type": plan_type.lower().replace(' ', '_'),
                "current_plan": selected_plan,
                "status": "created"
            }
            
            try:
                api_result = self.api_client.create_plan(plan_data)
                if api_result:
                    logger.info("📤 Plan uploaded to API successfully")
                    self.api_client.update_plan_status("in_progress")
            except Exception as e:
                logger.error(f"❌ API upload error: {str(e)}")
        
        # Initialize sub-agents
        self.init_sub_agents()
        
        # Execute plan
        execution_results = []
        completed_tasks = []
        failed_tasks = []
        
        try:
            for i, task in enumerate(selected_plan, 1):
                logger.info(colored(f"\n🚀 Executing Task {i}/{len(selected_plan)}: {task}", "cyan", attrs=["bold"]))
                
                if self.api_client:
                    self.api_client.update_task_status(task, "in_progress")
                
                # Execute task with ToolAgent
                token = state.get('token', '')
                try:
                    # Use ainvoke with proper async handling
                    import concurrent.futures
                    
                    def call_tool_agent(input_data):
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(self.tool_agent.ainvoke(input_data))
                        finally:
                            loop.close()
                    
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(call_tool_agent, {"input": task, "token": token})
                        tool_result = future.result(timeout=30)  # 30 second timeout
                    
                    tool_output = tool_result.get('output', '')
                    has_error = tool_result.get('error', '')
                    
                    if tool_output and not has_error:
                        execution_results.append({
                            "task_number": i,
                            "task": task,
                            "tool_execution": tool_output,
                            "status": "completed"
                        })
                        completed_tasks.append(task)
                        
                        if self.api_client:
                            self.api_client.update_task_status(task, "completed", tool_output)
                        
                        logger.info(colored(f"✅ Task {i} completed", "green"))
                    else:
                        error_msg = has_error or 'Unknown error'
                        execution_results.append({
                            "task_number": i,
                            "task": task,
                            "tool_execution": error_msg,
                            "status": "failed"
                        })
                        failed_tasks.append(task)
                        
                        if self.api_client:
                            self.api_client.update_task_status(task, "failed", error_msg)
                        
                        logger.error(colored(f"❌ Task {i} failed: {error_msg}", "red"))
                        
                except concurrent.futures.TimeoutError:
                    error_msg = "Task execution timed out after 30 seconds"
                    execution_results.append({
                        "task_number": i,
                        "task": task,
                        "tool_execution": error_msg,
                        "status": "failed"
                    })
                    failed_tasks.append(task)
                    
                    if self.api_client:
                        self.api_client.update_task_status(task, "failed", error_msg)
                    
                    logger.error(colored(f"❌ Task {i} timeout: {error_msg}", "red"))
                except Exception as e:
                    error_msg = f"Task execution error: {str(e)}"
                    execution_results.append({
                        "task_number": i,
                        "task": task,
                        "tool_execution": error_msg,
                        "status": "failed"
                    })
                    failed_tasks.append(task)
                    
                    if self.api_client:
                        self.api_client.update_task_status(task, "failed", error_msg)
                    
                    logger.error(colored(f"❌ Task {i} exception: {str(e)}", "red"))
        
        except Exception as e:
            logger.error(colored(f"❌ Critical error: {str(e)}", "red", attrs=["bold"]))
        
        # Finalize
        total_tasks = len(selected_plan)
        completed_count = len(completed_tasks)
        failed_count = len(failed_tasks)
        success_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0
        
        if self.api_client:
            final_status = "completed"
            final_summary = f"Completed {completed_count}/{total_tasks} tasks ({success_rate:.1f}%)"
            self.api_client.update_plan_status(final_status, final_summary)
        
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

    def invoke(self, input: str, selected_plan_id: int = None, plan_options: dict = None, token: str = None):
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
            'needs_user_selection': False,
            'selected_plan_id': selected_plan_id,
            'token': token,
            'output': ''
        }
        
        agent_response = self.graph.invoke(state)
        return agent_response

    def stream(self, input: str):
        pass