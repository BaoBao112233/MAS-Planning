from template.agent import BaseAgent
from template.configs.environments import env
from template.agent.meta.state import AgentState
from template.message.message import HumanMessage, SystemMessage
from template.message.converter import convert_messages_list
from template.agent.meta.utils import extract_from_xml
from template.agent.meta.prompt import META_PROMPT

from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph,END

from termcolor import colored
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',  # format thời gian
)
logger = logging.getLogger(__name__)

class MetaAgent(BaseAgent):
    def __init__(self, 
                 tools: list[dict] = [], 
                 model: str = "gemini-2.5-pro", 
                 temperature: float = 0.2, 
                 max_iteration: int = 10,
                 json_mode: bool = False,
                 verbose: bool = False,
                 llm=None):
        super().__init__()

        self.name = "Meta Agent"
        if llm:
            self.llm = llm
        else:
            self.llm = ChatVertexAI(
                model_name=model,
                temperature=temperature,
                project=env.GOOGLE_CLOUD_PROJECT,
                location=env.GOOGLE_CLOUD_LOCATION
            )

        self.tools = tools
        self.max_iteration = max_iteration
        self.json_mode = json_mode
        self.verbose = verbose
        self.iteration = 0
        self.system_prompt = META_PROMPT
        
        # Initialize graph
        self.graph = self.create_graph()
    
    def meta_expert(self,state:AgentState):
        # Convert custom messages to LangChain messages before passing to LLM
        messages = convert_messages_list(state['messages'])
        llm_response=self.llm.invoke(messages)
        # print(llm_response.content)
        agent_data=extract_from_xml(llm_response.content)
        logger.info(colored(f'Meta Agent extracted data: {agent_data}', 'blue'))
        name=agent_data.get('Agent Name')
        description=agent_data.get('Agent Description')
        tasks=agent_data.get('Tasks')
        tool=agent_data.get('Tool')
        answer=agent_data.get('Answer')
        if not answer:
            content=f'Agent Name: {name}\nDescription: {description}\nTasks: {tasks}\nTool: {tool}'
            print_stmt=colored(content,color='yellow',attrs=['bold'])
        else:
            content=f'Final Answer: {answer}'
            print_stmt=colored(content,color='cyan',attrs=['bold'])
        if self.verbose:
            print(print_stmt)
        return {**state,'agent_data':agent_data,'messages':[HumanMessage(content)]}

    def final(self,state:AgentState):
        if self.max_iteration>self.iteration:
            output=state['messages'][-1].content
        else:
            output='Iteration limit reached'
        return {**state, 'output':output}
    
    def controller(self,state:AgentState):
        if self.max_iteration>self.iteration:
            self.iteration+=1
            agent_data=state.get('agent_data')
            if agent_data and agent_data.get('Answer'):
                return 'Answer'
            else:
                return 'Answer'  # Default to Answer if no agent_data or no Answer
        else:
            return 'Answer'

    def create_graph(self):
        graph=StateGraph(AgentState)
        graph.add_node('Meta',self.meta_expert)
        # graph.add_node('React',self.react_expert)
        # graph.add_node('COT',self.cot_expert)
        graph.add_node('Answer',self.final)

        graph.set_entry_point('Meta')
        graph.add_conditional_edges('Meta',self.controller)
        # graph.add_edge('React','Meta')
        # graph.add_edge('COT','Meta')
        graph.add_edge('Answer',END)

        return graph.compile(debug=False)

    def invoke(self, input_data)->dict:    
        if self.verbose:
            print(f'Entering '+colored(self.name,'black','on_white'))  
        
        # Handle different input formats
        if isinstance(input_data, dict):
            # Convert dict to formatted string for MetaAgent
            task = input_data.get('task', '')
            context = input_data.get('context', '')
            previous_results = input_data.get('previous_results', [])
            
            input_text = f"Task: {task}\nContext: {context}"
            if previous_results:
                input_text += f"\nPrevious Results: {previous_results}"
        else:
            input_text = str(input_data)
            
        state={
            'input':input_text,
            'messages':[SystemMessage(self.system_prompt),HumanMessage(f'User Query: {input_text}')],
            'output':'',
        }
        graph_response=self.graph.invoke(state)
        
        # Return dict format for compatibility with PlanAgent
        return {
            'output': graph_response.get('output', ''),
            'agent_data': graph_response.get('agent_data', {}),
            'success': True
        }

    def stream(self, input: str):
        pass