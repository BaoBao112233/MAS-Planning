from template.agent import BaseAgent
from template.configs.environments import env
from template.agent.meta.state import AgentState
from template.message.message import HumanMessage, SystemMessage
from template.agent.meta.utils import extract_from_xml
from template.agent.meta.prompt import META_PROMPT

from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph,END

from termcolor import colored

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
        llm_response=self.llm.invoke(state['messages'])
        # print(llm_response.content)
        agent_data=extract_from_xml(llm_response.content)
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
            if agent_data.get('Answer'):
                return 'Answer'
            # elif agent_data.get('Tool'):
            #     return 'React'
            # else:
            #     return 'COT'
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

    def invoke(self, input: str)->str:    
        if self.verbose:
            print(f'Entering '+colored(self.name,'black','on_white'))  
        state={
            'input':input,
            'messages':[SystemMessage(self.system_prompt),HumanMessage(f'User Query: {input}')],
            'output':'',
        }
        graph_response=self.graph.invoke(state)
        return graph_response['output']

    def stream(self, input: str):
        pass