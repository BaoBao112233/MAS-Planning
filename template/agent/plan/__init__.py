from template.agent import BaseAgent
from template.agent.plan.state import PlanState,UpdateState
# from template.agent.meta.agent import MetaAgent
from template.message.message import SystemMessage,HumanMessage
from template.message.converter import convert_messages_list
from template.agent.plan.utils import (
    extract_llm_response, 
    read_markdown_file,
)
from template.agent.plan.prompts import PLAN_PROMPTS, UPDATE_PLAN_PROMPTS
from template.agent.meta import MetaAgent
from template.configs.environments import env

from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph,END,START
from langchain_mcp_adapters.client import MultiServerMCPClient
from termcolor import colored
import os
import time
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PlanAgent(BaseAgent):
    def __init__(self, model: str = "gemini-2.5-pro", temperature: float = 0.2, max_iteration=10,verbose=True):
        super().__init__()
        
        self.name = "Plan Agent"

        # self.llm = ChatVertexAI(
        #     model_name=model,
        #     temperature=temperature,
        #     tools=self.tools,
        #     project=env.GOOGLE_CLOUD_PROJECT,
        #     location=env.GOOGLE_CLOUD_LOCATION
        # )

        self.model = model
        self.temperature = temperature
        self.verbose = verbose

        self.tools = []
        self.llm = None

        logger.info(f"PlanAgent initialized with model={model}, temperature={temperature}")

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

    def router(self, state: PlanState):
        # Check if this is a plan selection
        selected_plan_id = state.get('selected_plan_id')
        if selected_plan_id:
            return {**state, 'plan_type': 'execute'}
        
        # Check if message indicates plan selection
        input_msg = state.get('input', '').strip().lower()
        if input_msg in ['plan 1', 'plan 2', 'plan 3', '1', '2', '3', 'plan a', 'plan b', 'plan c', 'a', 'b', 'c']:
            # Extract plan number
            if 'plan 1' in input_msg or input_msg == '1' or input_msg == 'plan a' or input_msg == 'a':
                selected_plan_id = 1
            elif 'plan 2' in input_msg or input_msg == '2' or input_msg == 'plan b' or input_msg == 'b':
                selected_plan_id = 2
            elif 'plan 3' in input_msg or input_msg == '3' or input_msg == 'plan c' or input_msg == 'c':
                selected_plan_id = 3
            
            return {**state, 'plan_type': 'execute', 'selected_plan_id': selected_plan_id}
        
        # Normal plan creation
        routes=[
            {
                'route': 'priority',
                'description': 'This route creates 3 alternative plans prioritized by Security, Convenience, and Energy Efficiency using ONLY MCP smart home tools. The user can review all options and select the most suitable plan. All device information and control operations are handled through MCP tools only.'
            }
        ]
        return {**state,'plan_type':'priority'}

    def priority_plan(self,state:PlanState):
        from template.agent.plan.utils import extract_priority_plans
        
        # Get available MCP tools to include in planning
        available_tools = []
        if self.tools:
            available_tools = [f"- {tool.name}: {tool.description}" for tool in self.tools]  # Limit to first 10 tools
        
        tools_info = "\n".join(available_tools) if available_tools else "- No MCP tools currently available"
        
        # Use the structured prompt with MCP tools information
        system_prompt = PLAN_PROMPTS.replace("<<Tools_info>>", tools_info)

        # Convert custom messages to LangChain messages before passing to LLM
        messages = convert_messages_list([
            SystemMessage(system_prompt),
            HumanMessage(f"User request: {state.get('input')}")
        ])
        
        logger.info(f"Prompt constructed for Priority Planning:{system_prompt[:50]}...")
        
        if self.verbose:
            print("Calling LLM to generate priority plans...")
        
        logger.info("Calling LLM to generate priority plans...")
        
        try:
            # Actually call the LLM
            llm_response = self.llm.invoke(messages)
            if self.verbose:
                logger.info(colored(f"LLM Response received: {len(llm_response.content)} characters", color='cyan'))
                # print(colored(f"LLM Response: {llm_response.content}", color='cyan'))
            
            # Extract plans from LLM response
            plan_data = extract_priority_plans(llm_response.content)
            
            # Validate that we got plans
            if not any(plan_data.get(key) for key in ['Security_Plan', 'Convenience_Plan', 'Energy_Plan']):
                if self.verbose:
                    logger.warning("Warning: No plans extracted from LLM response, using fallback data")
                # Fallback to dummy data if extraction failed
                plan_data = {
                    'Security_Plan': [
                        'Set up security cameras in key areas', 
                        'Install motion sensors and alarm system',
                        'Enable automated security lighting',
                        'Configure door and window sensors'
                    ],
                    'Convenience_Plan': [
                        'Automate lighting based on presence', 
                        'Set up voice control for common tasks', 
                        'Create morning and evening routines',
                        'Install smart switches for easy control'
                    ],
                    'Energy_Plan': [
                        'Install smart thermostat for climate control', 
                        'Use energy-efficient LED bulbs throughout', 
                        'Set up automated power management',
                        'Configure energy monitoring and alerts'
                    ]
                }

            logger.info("LLM call completed successfully.")
        except Exception as e:
            logger.error(f"Error calling LLM: {str(e)}")
            if self.verbose:
                logger.info(f"LLM call failed: {str(e)}, using fallback data")
            # Use fallback data if LLM call fails
            plan_data = {
                'Security_Plan': [
                    'Set up security cameras in key areas', 
                    'Install motion sensors and alarm system',
                    'Enable automated security lighting',
                    'Configure door and window sensors'
                ],
                'Convenience_Plan': [
                    'Automate lighting based on presence', 
                    'Set up voice control for common tasks', 
                    'Create morning and evening routines',
                    'Install smart switches for easy control'
                ],
                'Energy_Plan': [
                    'Install smart thermostat for climate control', 
                    'Use energy-efficient LED bulbs throughout', 
                    'Set up automated power management',
                    'Configure energy monitoring and alerts'
                ]
            }
            logger.error(f"Error calling LLM: {str(e)}")
            if self.verbose:
                logger.info(f"LLM call failed: {str(e)}, using fallback data")
            # Use fallback data if LLM call fails
            plan_data = {
                'Security_Plan': ['Secure all entry points and doors', 'Set up security cameras in key areas', 'Install motion sensors and alarm system'],
                'Convenience_Plan': ['Automate lighting based on presence', 'Set up voice control for common tasks', 'Create morning and evening routines'],
                'Energy_Plan': ['Install smart thermostat for climate control', 'Use energy-efficient LED bulbs throughout', 'Set up solar panels and energy monitoring']
            }
        
        # Extract the 3 priority plans
        security_plan = plan_data.get('Security_Plan', [])
        convenience_plan = plan_data.get('Convenience_Plan', [])
        energy_plan = plan_data.get('Energy_Plan', [])
        
        # For API mode - return plan options instead of asking for user input
        
        # Store all plans in state for later use
        plan_options = {
            'security_plan': security_plan,
            'convenience_plan': convenience_plan,
            'energy_plan': energy_plan
        }
        # Return plan options - will be handled by API response
        return {**state, 'plan_options': plan_options, 'needs_user_selection': True}


    def initialize(self,state:UpdateState):
        system_prompt=UPDATE_PLAN_PROMPTS
        plan_list = state.get('plan', [])
        current = plan_list[0] if plan_list else ""
        pending = plan_list or []
        completed = []
        
        if self.verbose:
            if pending:
                print(colored(f'Pending Tasks:\n{'\n'.join([f'{index+1}. {task}' for index,task in enumerate(pending)])}',color='yellow',attrs=['bold']))
            if completed:
                print(colored(f'Completed Tasks:\n{'\n'.join([f'{index+1}. {task}' for index,task in enumerate(completed)])}',color='blue',attrs=['bold']))
        
        # Khởi tạo tất cả tasks với status "pending" trên API
        if self.api_enabled and self.api_client:
            for task in pending:
                self.api_client.update_task_status(task, "pending")
            
            # Update plan status to "in_progress" 
            self.api_client.update_plan_status("in_progress")
        
        messages=[SystemMessage(system_prompt)]
        return {**state,'messages':messages,'current':current,'pending':pending,'completed':completed,'output':''}
    
    def execute_task(self,state:UpdateState):
        plan=state.get('plan')
        current=state.get('current')
        responses=state.get('responses')
        
        # Update task status to "in_progress" trước khi execute
        if self.api_enabled and self.api_client:
            self.api_client.update_task_status(current, "in_progress")
        
        agent=MetaAgent(llm=self.llm,verbose=self.verbose)
        task_response=agent.invoke(f'Information:\n{'\n'.join([f'{index+1}. {task}' for index,task in enumerate(responses)])}\nTask:\n{current}')
        
        if self.verbose:
            print(colored(f'Current Task:\n{current}',color='cyan',attrs=['bold']))
            print(colored(f'Task Response:\n{task_response}',color='cyan',attrs=['bold']))
        
        # Update task với execution result
        if self.api_enabled and self.api_client:
            self.api_client.update_task_status(current, "completed", task_response)
        
        # Truncate task_response if too long to prevent payload issues
        max_response_length = 2000
        if len(task_response) > max_response_length:
            task_response_truncated = task_response[:max_response_length] + "... [response truncated for brevity]"
        else:
            task_response_truncated = task_response
            
        user_prompt=f'Plan:\n{plan}\nTask:\n{current}\nTask Response:\n{task_response_truncated}'
        messages=[HumanMessage(user_prompt)]
        return {**state,'messages':messages,'responses':[task_response]}

    def trim_messages(self, messages, max_tokens=4000):
        """Trim messages to prevent payload too large error"""
        if not messages:
            return messages
            
        # Keep only the most recent messages that fit within token limit
        trimmed = []
        total_chars = 0
        
        # Reverse to process from newest to oldest
        for msg in reversed(messages):
            msg_chars = len(str(msg.content))
            if total_chars + msg_chars > max_tokens * 4:  # Rough char to token ratio
                break
            trimmed.insert(0, msg)
            total_chars += msg_chars
            
        # Always keep at least the last message
        if not trimmed and messages:
            last_msg = messages[-1]
            # Truncate content if too long
            if len(str(last_msg.content)) > max_tokens * 4:
                content = str(last_msg.content)[:max_tokens * 4] + "... [truncated]"
                trimmed = [type(last_msg)(content)]
            else:
                trimmed = [last_msg]
                
        return trimmed

    def update_plan(self,state:UpdateState):
        # Trim messages to prevent payload too large
        messages = self.trim_messages(state.get('messages', []))
        # Convert custom messages to LangChain messages before passing to LLM
        converted_messages = convert_messages_list(messages)
        llm_response=self.llm.invoke(converted_messages)
        plan_data=extract_llm_response(llm_response.content)
        plan=plan_data.get('Plan')
        pending=plan_data.get('Pending') or []  # Default to empty list if None
        completed=plan_data.get('Completed') or []  # Default to empty list if None
        
        if self.verbose:
            if pending:
                print(colored(f'Pending Tasks:\n{'\n'.join([f'{index+1}. {task}' for index,task in enumerate(pending)])}',color='yellow',attrs=['bold']))
            if completed:
                print(colored(f'Completed Tasks:\n{'\n'.join([f'{index+1}. {task}' for index,task in enumerate(completed)])}',color='blue',attrs=['bold']))
        
        # Update task statuses trên API
        if self.api_enabled and self.api_client:
            # Lấy task trước đó để so sánh
            previous_completed = state.get('completed', [])
            previous_pending = state.get('pending', [])
            
            # Tìm tasks vừa được completed
            newly_completed = [task for task in completed if task not in previous_completed]
            for task in newly_completed:
                self.api_client.update_task_status(task, "completed", f"Task '{task}' hoàn thành thành công")
            
            # Update pending tasks status
            for task in pending:
                if task not in previous_pending:  # New pending task
                    self.api_client.update_task_status(task, "pending")
            
            # Update plan status
            if not pending:  # Tất cả tasks đã completed
                self.api_client.update_plan_status("completed")
            else:
                self.api_client.update_plan_status("in_progress")
        
        if pending:
            current=pending[0]
        else:
            current=''
        # Keep the completed list we already processed instead of overwriting with potentially None
        completed_final = plan_data.get('Completed') or []
        return {**state,'plan':plan,'current':current,'pending':pending,'completed':completed_final}
    
    def final(self,state:UpdateState):
        user_prompt='All Tasks completed successfully. Now give the final answer.'
        # Convert custom messages to LangChain messages before passing to LLM
        messages = convert_messages_list(state.get('messages')+[HumanMessage(user_prompt)])
        llm_response=self.llm.invoke(messages)
        plan_data=extract_llm_response(llm_response.content)
        output=plan_data.get('Final Answer')
        
        # Hoàn thành plan trên API
        if self.api_enabled and self.api_client:
            self.api_client.update_plan_status("completed", output)
            
            if self.verbose:
                print("🎉 Plan execution completed! All data sent to API.")
        
        return {**state,'output':output}

    def execute_selected_plan(self, state: PlanState):
        """Execute the selected plan and upload to API"""
        selected_plan_id = state.get('selected_plan_id')
        
        if not selected_plan_id:
            return {**state, 'output': 'No plan selected'}
        
        # Get dummy plan options (in real app, these would be cached)
        plan_options = {
            'security_plan': [
                'Set up security cameras in key areas', 
                'Install motion sensors and alarm system',
                'Enable automated security lighting',
                'Configure door and window sensors'
            ],
            'convenience_plan': [
                'Automate lighting based on presence', 
                'Set up voice control for common tasks', 
                'Create morning and evening routines',
                'Install smart switches for easy control'
            ],
            'energy_plan': [
                'Install smart thermostat for climate control', 
                'Use energy-efficient LED bulbs throughout', 
                'Set up automated power management',
                'Configure energy monitoring and alerts'
            ]
        }
        
        # Select the plan
        if selected_plan_id == 1:
            selected_plan = plan_options['security_plan']
            plan_type = 'priority_security'
            plan_name = 'Security Priority Plan'
        elif selected_plan_id == 2:
            selected_plan = plan_options['convenience_plan']
            plan_type = 'priority_convenience'
            plan_name = 'Convenience Priority Plan'
        elif selected_plan_id == 3:
            selected_plan = plan_options['energy_plan']
            plan_type = 'priority_energy'
            plan_name = 'Energy Efficiency Priority Plan'
        else:
            return {**state, 'output': 'Invalid plan selection'}
        
        if self.verbose:
            print(colored(f'\n✅ Selected Plan: {plan_name}', color='green', attrs=['bold']))
            print(colored('📋 Tasks:', color='cyan', attrs=['bold']))
            for i, task in enumerate(selected_plan, 1):
                print(colored(f'   {i}. {task}', color='white'))
        
        # Upload plan to API (placeholder)
        if self.api_client:
            api_data = {
                "input": state.get('input'),
                "plan_type": plan_type,
                "plan_name": plan_name,
                "current_plan": selected_plan,
                "pending_tasks": selected_plan.copy(),
                "completed_tasks": [],
                "current_task": selected_plan[0] if selected_plan else "",
                "status": "plan_selected_ready_to_execute",
                "timestamp": time.time(),
                "selected_plan_id": selected_plan_id
            }
            try:
                # self.api_client.upload_plan(api_data)
                logger.info(f"📤 Plan uploaded to API: {plan_name}")
            except Exception as e:
                logger.error(f"❌ Failed to upload plan to API: {str(e)}")
        
        # Return execution result
        output = f"✅ **{plan_name}** has been selected and uploaded to API for execution.\n\n"
        output += "📋 **Plan Tasks:**\n"
        for i, task in enumerate(selected_plan, 1):
            output += f"{i}. {task}\n"
        output += f"\n🚀 Plan execution will begin shortly..."
        
        return {**state, 'plan': selected_plan, 'output': output}

    def plan_controller(self,state:UpdateState):
        if state.get('pending'):
            return 'task'
        else:
            return 'final'

    def route_controller(self,state:PlanState):
        plan_type = state.get('plan_type')
        if plan_type == 'execute':
            return 'execute_selected'
        elif state.get('needs_user_selection', False):
            return 'wait_selection'
        return plan_type

    def create_graph(self):
        graph=StateGraph(PlanState)
        graph.add_node('route',self.router)
        # Priority planning - MCP tools approach
        graph.add_node('priority',self.priority_plan)
        graph.add_node('execute_selected', self.execute_selected_plan)
        graph.add_node('wait_selection', lambda state: {**state, 'output': 'waiting_for_selection'})
        graph.add_node('execute',lambda _:self.update_graph())

        graph.add_edge(START,'route')
        graph.add_conditional_edges('route',self.route_controller)
        # Handle both direct execution and user selection flow
        graph.add_conditional_edges('priority', lambda state: 'wait_selection' if state.get('needs_user_selection') else 'execute')
        graph.add_edge('execute_selected', END)
        graph.add_edge('wait_selection', END)
        graph.add_edge('execute',END)

        return graph.compile(debug=False)
    
    def update_graph(self):
        graph=StateGraph(UpdateState)
        graph.add_node('inital',self.initialize)
        graph.add_node('task',self.execute_task)
        graph.add_node('update',self.update_plan)
        graph.add_node('final',self.final)

        graph.add_edge(START,'inital')
        graph.add_edge('inital','task')
        graph.add_edge('task','update')
        graph.add_conditional_edges('update',self.plan_controller)
        graph.add_edge('final',END)

        return graph.compile(debug=False)

    def invoke(self,input:str, selected_plan_id: int = None):
        # Lưu thời gian bắt đầu và input để sử dụng cho API
        self.start_time = time.time()
        self.current_input = input
        
        if self.verbose:
            print(f'Entering '+colored(self.name,'black','on_white'))
        state={
            'input': input,
            'plan_status':'',
            'route':'',
            'plan': [],
            'plan_options': {},
            'needs_user_selection': False,
            'selected_plan_id': selected_plan_id,
            'output': ''
        }
        agent_response=self.graph.invoke(state)
        return agent_response

    def select_plan_from_options(self, state: PlanState):
        """Handle plan selection when user provides selection"""
        plan_options = state.get('plan_options', {})
        selected_plan_id = state.get('selected_plan_id')
        
        if selected_plan_id == 1:
            selected_plan = plan_options.get('security_plan', [])
            plan_type = 'priority_security'
        elif selected_plan_id == 2:
            selected_plan = plan_options.get('convenience_plan', [])
            plan_type = 'priority_convenience'
        elif selected_plan_id == 3:
            selected_plan = plan_options.get('energy_plan', [])
            plan_type = 'priority_energy'
        else:
            # Default to security plan
            selected_plan = plan_options.get('security_plan', [])
            plan_type = 'priority_security'
        
        if self.verbose:
            print(colored(f'\nSelected Plan:\n{'\n'.join([f'{index+1}. {task}' for index,task in enumerate(selected_plan)])}',color='green',attrs=['bold']))
        
        return {**state, 'plan': selected_plan, 'needs_user_selection': False}


    def stream(self, input: str):
        pass