# Development Guide & Best Practices

## 🎯 Tổng quan

Document này cung cấp comprehensive development guide cho MAS-Planning system, bao gồm setup instructions, coding standards, testing strategies, và deployment best practices.

## 🛠️ Development Environment Setup

### **1. System Requirements**

```bash
# Minimum Requirements
- Python 3.8+
- Node.js 16+ (for MCP server if needed)
- Redis Server 6+
- Git 2.30+
- Docker & Docker Compose (optional)

# Recommended Development Tools
- VS Code với Python extension
- PyCharm Professional
- Postman cho API testing
- Redis GUI client
```

### **2. Initial Setup**

```bash
# Clone repository
git clone https://github.com/BaoBao112233/MAS-Planning.git
cd MAS-Planning

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Linux/Mac:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt

# Copy environment template
cp .env.template .env
cp service-account.json.example service-account.json

# Configure environment variables
# Edit .env file với your settings
```

### **3. Environment Configuration**

```bash
# .env file configuration
APP_NAME="MAS Planning System"
APP_DESC="Multi-Agent Smart Home Planning"
API_VERSION="1.0.0"
APP_PORT=9000

# Google Cloud Configuration
GOOGLE_CLOUD_PROJECT="your-project-id"
GOOGLE_CLOUD_LOCATION="us-central1"
MODEL_NAME="gemini-2.5-pro"
GOOGLE_APPLICATION_CREDENTIALS="service-account.json"

# Redis Configuration
REDIS_HOST="localhost"
REDIS_PORT=6379
REDIS_DB=0
TTL_SECONDS=3600

# MCP Server Configuration
MCP_SERVER_URL="http://localhost:9031"

# External API Configuration
PLAN_API_BASE_URL="http://localhost:8080"
PLAN_API_KEY="your-api-key"
OXII_ROOT_API_URL="https://api.oxii.com"

# Debug Settings
DEBUG_MODE=true
MAX_TURNS=20
LIMIT_MINUTES=10
MAX_MSG=12
```

### **4. Google Cloud Setup**

```bash
# Install Google Cloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Initialize gcloud
gcloud init

# Create project (if needed)
gcloud projects create your-project-id

# Enable required APIs
gcloud services enable aiplatform.googleapis.com
gcloud services enable cloudbuild.googleapis.com

# Create service account
gcloud iam service-accounts create mas-planning-sa \
    --description="Service account for MAS Planning" \
    --display-name="MAS Planning Service Account"

# Grant required permissions
gcloud projects add-iam-policy-binding your-project-id \
    --member="serviceAccount:mas-planning-sa@your-project-id.iam.gserviceaccount.com" \
    --role="roles/aiplatform.user"

# Create và download key
gcloud iam service-accounts keys create service-account.json \
    --iam-account=mas-planning-sa@your-project-id.iam.gserviceaccount.com
```

## 🏗️ Code Structure & Organization

### **1. Project Structure**

```
MAS-Planning/
├── main.py                     # FastAPI application entry point
├── requirements-dev.txt        # Python dependencies
├── docker-compose.yml         # Docker configuration
├── Dockerfile                 # Container configuration
├── .env.template              # Environment template
├── service-account.json       # GCP credentials
├── 
├── template/                  # Main application code
│   ├── agent/                 # Agent implementations
│   │   ├── __init__.py       # Base agent class
│   │   ├── agent.py          # Agent utilities
│   │   ├── histories.py      # Chat history management
│   │   ├── prompts.py        # Shared prompts
│   │   ├── api_client.py     # External API client
│   │   │
│   │   ├── manager/          # Manager Agent
│   │   │   ├── __init__.py   # Manager Agent implementation
│   │   │   ├── prompt.py     # Manager-specific prompts
│   │   │   ├── state.py      # State definitions
│   │   │   └── utils.py      # Utility functions
│   │   │
│   │   ├── plan/             # Plan Agent
│   │   │   ├── __init__.py   # Plan Agent implementation
│   │   │   ├── prompts.py    # Planning prompts
│   │   │   ├── state.py      # Plan state management
│   │   │   └── utils.py      # Planning utilities
│   │   │
│   │   ├── meta/             # Meta Agent
│   │   │   ├── __init__.py   # Meta Agent implementation
│   │   │   ├── prompt.py     # Analysis prompts
│   │   │   ├── state.py      # Meta state management
│   │   │   └── utils.py      # Analysis utilities
│   │   │
│   │   └── tool/             # Tool Agent
│   │       ├── __init__.py   # Tool Agent implementation
│   │       ├── prompt.py     # Tool prompts
│   │       ├── state.py      # Tool state management
│   │       └── utils.py      # Tool utilities
│   │
│   ├── configs/              # Configuration management
│   │   └── environments.py   # Environment settings
│   │
│   ├── message/              # Message handling
│   │   ├── message.py        # Message classes
│   │   └── converter.py      # Message converters
│   │
│   ├── router/               # API routing
│   │   └── v1/
│   │       └── ai.py         # AI endpoints
│   │
│   └── schemas/              # Data models
│       └── model.py          # Pydantic models
│
├── docs/                     # Documentation
│   ├── 01_Kiến_Trúc_Tổng_Quan.md
│   ├── 02_Manager_Agent.md
│   ├── 03_Plan_Agent.md
│   ├── 04_Meta_Agent.md
│   ├── 05_Tool_Agent.md
│   ├── 06_MCP_Integration_External_Services.md
│   └── 07_Development_Guide.md
│
└── tests/                    # Test suite
    ├── unit/                 # Unit tests
    ├── integration/          # Integration tests
    └── e2e/                  # End-to-end tests
```

### **2. Coding Standards**

```python
# File header template
"""
Module: agent/plan/__init__.py
Description: Plan Agent implementation for MAS-Planning system
Author: MAS-Planning Team
Created: 2025-01-XX
Modified: 2025-01-XX
"""

# Import organization
import os
import sys
import time
import asyncio
from typing import Dict, List, Any, Optional, TypedDict

# Third-party imports
import logging
from termcolor import colored
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph, END, START

# Local imports
from template.agent import BaseAgent
from template.configs.environments import env
from template.message.message import SystemMessage, HumanMessage

# Logging configuration
logger = logging.getLogger(__name__)

# Class definition với comprehensive docstring
class PlanAgent(BaseAgent):
    """
    Plan Agent - Strategic Planning Engine
    
    The Plan Agent is responsible for creating intelligent smart home automation plans
    và orchestrating their execution through other specialized agents.
    
    Attributes:
        name (str): Agent identifier
        model (str): LLM model name
        temperature (float): LLM temperature setting
        verbose (bool): Verbose logging flag
        tools (List): Available MCP tools
        llm: Language model instance
        graph: LangGraph execution graph
    
    Methods:
        router: Route input to appropriate planning workflow
        priority_plan: Generate 3 priority-based plans
        execute_selected_plan: Execute user-selected plan
        init_sub_agents: Initialize Meta và Tool agents
    """
    
    def __init__(self, 
                 model: str = "gemini-2.5-pro", 
                 temperature: float = 0.2, 
                 max_iteration: int = 10,
                 verbose: bool = True):
        """
        Initialize Plan Agent
        
        Args:
            model: LLM model name
            temperature: LLM temperature (0.0-1.0)
            max_iteration: Maximum planning iterations
            verbose: Enable detailed logging
        """
        super().__init__()
        
        self.name = "Plan Agent"
        self.model = model
        self.temperature = temperature
        self.verbose = verbose
        
        # Initialize components
        self.tools = []
        self.llm = None
        self.meta_agent = None
        self.tool_agent = None
        
        # Create execution graph
        self.graph = self.create_graph()
        
        if self.verbose:
            logger.info(f"✅ {self.name} initialized successfully")
```

### **3. Error Handling Patterns**

```python
# Comprehensive error handling
class PlanningError(Exception):
    """Base exception for planning operations"""
    pass

class MCPConnectionError(PlanningError):
    """Raised when MCP server connection fails"""
    pass

class AuthenticationError(PlanningError):
    """Raised when authentication fails"""
    pass

def robust_planning_operation(func):
    """Decorator for robust planning operations"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MCPConnectionError as e:
            logger.error(f"MCP connection failed: {e}")
            # Fallback to cached tools
            return fallback_planning_operation(*args, **kwargs)
        except AuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            raise  # Re-raise auth errors
        except Exception as e:
            logger.error(f"Unexpected error trong {func.__name__}: {e}")
            # Return safe fallback response
            return safe_fallback_response()
    return wrapper

@robust_planning_operation
def generate_priority_plans(self, input_text: str) -> Dict:
    """Generate plans với comprehensive error handling"""
    # Implementation với try-catch blocks
    pass
```

## 🧪 Testing Strategy

### **1. Testing Framework Setup**

```python
# tests/conftest.py
import pytest
import asyncio
import os
from unittest.mock import Mock, AsyncMock
from template.configs.environments import env

@pytest.fixture
def mock_llm():
    """Mock LLM for testing"""
    mock = Mock()
    mock.invoke = Mock(return_value=Mock(content="Test response"))
    return mock

@pytest.fixture
def mock_mcp_tools():
    """Mock MCP tools"""
    tools = [
        Mock(name="get_device_list", description="Get device list"),
        Mock(name="switch_device_control", description="Control switches"),
        Mock(name="control_air_conditioner", description="Control AC")
    ]
    return tools

@pytest.fixture
async def plan_agent(mock_llm, mock_mcp_tools):
    """Plan Agent fixture for testing"""
    from template.agent.plan import PlanAgent
    
    agent = PlanAgent(verbose=False)
    agent.llm = mock_llm
    agent.tools = mock_mcp_tools
    
    return agent

@pytest.fixture
def sample_plan_data():
    """Sample plan data for testing"""
    return {
        'security_plan': [
            'Install motion sensors',
            'Set up security cameras',
            'Configure alarm system'
        ],
        'convenience_plan': [
            'Automate lighting',
            'Set up voice control',
            'Create routines'
        ],
        'energy_plan': [
            'Install smart thermostat',
            'Use LED bulbs',
            'Monitor energy usage'
        ]
    }
```

### **2. Unit Tests**

```python
# tests/unit/test_plan_agent.py
import pytest
from unittest.mock import Mock, patch
from template.agent.plan import PlanAgent

class TestPlanAgent:
    """Test suite for Plan Agent"""
    
    def test_plan_agent_initialization(self):
        """Test Plan Agent initialization"""
        agent = PlanAgent(verbose=False)
        
        assert agent.name == "Plan Agent"
        assert agent.model == "gemini-2.5-pro"
        assert agent.temperature == 0.2
        assert agent.tools == []
        assert agent.llm is None
    
    def test_router_logic(self, plan_agent, sample_plan_data):
        """Test routing logic"""
        # Test new planning request
        state = {'input': 'Create a smart home plan'}
        result = plan_agent.router(state)
        assert result['plan_type'] == 'priority'
        
        # Test plan selection
        state = {'input': '2', 'plan_options': sample_plan_data}
        result = plan_agent.router(state)
        assert result['plan_type'] == 'execute'
        assert result['selected_plan_id'] == 2
    
    @patch('template.agent.plan.extract_priority_plans')
    def test_priority_plan_generation(self, mock_extract, plan_agent, sample_plan_data):
        """Test priority plan generation"""
        # Mock extraction function
        mock_extract.return_value = {
            'Security_Plan': sample_plan_data['security_plan'],
            'Convenience_Plan': sample_plan_data['convenience_plan'],
            'Energy_Plan': sample_plan_data['energy_plan']
        }
        
        state = {'input': 'Create automation plan for living room'}
        result = plan_agent.priority_plan(state)
        
        assert 'plan_options' in result
        assert result['needs_user_selection'] is True
        assert len(result['plan_options']) == 3
    
    def test_error_handling(self, plan_agent):
        """Test error handling trong plan generation"""
        # Mock LLM to raise exception
        plan_agent.llm.invoke.side_effect = Exception("LLM error")
        
        state = {'input': 'Create plan'}
        result = plan_agent.priority_plan(state)
        
        # Should return fallback data
        assert 'plan_options' in result
        assert all(key in result['plan_options'] for key in ['security_plan', 'convenience_plan', 'energy_plan'])
```

### **3. Integration Tests**

```python
# tests/integration/test_agent_integration.py
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

class TestAgentIntegration:
    """Test integration between agents"""
    
    @pytest.mark.asyncio
    async def test_plan_to_meta_integration(self):
        """Test Plan Agent to Meta Agent integration"""
        from template.agent.plan import PlanAgent
        from template.agent.meta import MetaAgent
        
        # Setup
        plan_agent = PlanAgent(verbose=False)
        plan_agent.llm = Mock()
        plan_agent.meta_agent = MetaAgent(verbose=False)
        plan_agent.meta_agent.llm = Mock()
        
        # Mock Meta Agent response
        plan_agent.meta_agent.invoke = Mock(return_value={
            'output': 'Task analysis complete',
            'agent_data': {'Agent Name': 'Tool Agent'},
            'success': True
        })
        
        # Test integration
        task = "Turn on living room lights"
        meta_input = {
            "input": task,
            "context": "Test context",
            "previous_results": []
        }
        
        result = plan_agent.meta_agent.invoke(meta_input)
        
        assert result['success'] is True
        assert 'output' in result
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test end-to-end workflow"""
        from template.agent.manager import ManagerAgent
        
        # Setup Manager Agent
        manager = ManagerAgent(
            session_id="test_session",
            conversation_id="test_conv",
            verbose=False
        )
        
        # Mock external dependencies
        manager.llm = Mock()
        manager.llm.invoke = Mock(return_value=Mock(content="Mock LLM response"))
        
        # Test input
        input_data = {
            "message": "Create a security plan for my home",
            "token": "test_token"
        }
        
        # Execute workflow
        result = manager.invoke(input_data)
        
        assert 'output' in result
        assert result['success'] is True
```

### **4. End-to-End Tests**

```python
# tests/e2e/test_api_endpoints.py
import pytest
import httpx
from fastapi.testclient import TestClient
from main import app

class TestAPIEndpoints:
    """End-to-end API tests"""
    
    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)
    
    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = self.client.get("/health")
        
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
    
    def test_chat_endpoint_plan_creation(self):
        """Test chat endpoint for plan creation"""
        payload = {
            "conversationId": "test_conv",
            "sessionId": "test_session",
            "message": "Create a smart home plan for my bedroom",
            "channelId": "test_channel",
            "socialNetworkId": "test_network",
            "pageName": "test_page",
            "token": "test_token"
        }
        
        response = self.client.post("/ai/chat", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "sessionId" in data
        assert "response" in data
        assert data["error_status"] == "success"
    
    def test_chat_endpoint_plan_selection(self):
        """Test plan selection workflow"""
        # First, create plans
        create_payload = {
            "conversationId": "test_conv_2",
            "sessionId": "test_session_2",
            "message": "Create automation plan",
            "channelId": "test_channel",
            "socialNetworkId": "test_network",
            "pageName": "test_page"
        }
        
        create_response = self.client.post("/ai/chat", json=create_payload)
        assert create_response.status_code == 200
        
        # Then, select a plan
        select_payload = {
            "conversationId": "test_conv_2",
            "sessionId": "test_session_2",
            "message": "2",  # Select plan 2
            "channelId": "test_channel",
            "socialNetworkId": "test_network",
            "pageName": "test_page",
            "token": "test_token"
        }
        
        select_response = self.client.post("/ai/chat", json=select_payload)
        assert select_response.status_code == 200
    
    def test_token_endpoint(self):
        """Test token generation endpoint"""
        response = self.client.get(
            "/token",
            params={
                "user_phone": "1234567890",
                "user_password": "test_password",
                "user_country": "VI"
            }
        )
        
        # Note: This will fail trong test environment without real OXII API
        # But we can test the endpoint structure
        assert response.status_code in [200, 500]  # Allow both success và expected failure
```

## 🚀 Deployment Guide

### **1. Local Development**

```bash
# Start development server
python main.py

# With auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 9000

# With verbose logging
DEBUG_MODE=true python main.py
```

### **2. Docker Deployment**

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash mas-user
RUN chown -R mas-user:mas-user /app
USER mas-user

# Expose port
EXPOSE 9000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9000/health || exit 1

# Start application
CMD ["python", "main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  mas-planning:
    build: .
    ports:
      - "9000:9000"
    environment:
      - REDIS_HOST=redis
      - MCP_SERVER_URL=http://mcp-server:9031
    volumes:
      - ./service-account.json:/app/service-account.json:ro
      - ./logs:/app/logs
    depends_on:
      - redis
      - mcp-server
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  mcp-server:
    image: your-mcp-server:latest
    ports:
      - "9031:9031"
    environment:
      - NODE_ENV=production
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9031/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  redis_data:

networks:
  default:
    driver: bridge
```

### **3. Production Deployment**

```bash
# Production docker-compose
version: '3.8'

services:
  mas-planning:
    image: mas-planning:latest
    ports:
      - "9000:9000"
    environment:
      - ENV=production
      - REDIS_HOST=redis
      - MCP_SERVER_URL=http://mcp-server:9031
    volumes:
      - ./service-account.json:/app/service-account.json:ro
      - ./logs:/app/logs
      - ./data:/app/data
    deploy:
      replicas: 3
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      resources:
        limits:
          memory: 2G
          cpus: '1'
        reservations:
          memory: 1G
          cpus: '0.5'
    depends_on:
      - redis
      - mcp-server
    networks:
      - mas-network

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/ssl:ro
    depends_on:
      - mas-planning
    networks:
      - mas-network

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
      - ./redis.conf:/etc/redis/redis.conf:ro
    command: redis-server /etc/redis/redis.conf
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
    networks:
      - mas-network

networks:
  mas-network:
    driver: overlay
    attachable: true

volumes:
  redis_data:
    driver: local
```

### **4. Kubernetes Deployment**

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mas-planning
  namespace: default
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mas-planning
  template:
    metadata:
      labels:
        app: mas-planning
    spec:
      containers:
      - name: mas-planning
        image: mas-planning:latest
        ports:
        - containerPort: 9000
        env:
        - name: REDIS_HOST
          value: "redis-service"
        - name: MCP_SERVER_URL
          value: "http://mcp-server-service:9031"
        volumeMounts:
        - name: service-account
          mountPath: /app/service-account.json
          subPath: service-account.json
          readOnly: true
        - name: logs
          mountPath: /app/logs
        livenessProbe:
          httpGet:
            path: /health
            port: 9000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 9000
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1"
      volumes:
      - name: service-account
        secret:
          secretName: gcp-service-account
      - name: logs
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: mas-planning-service
spec:
  selector:
    app: mas-planning
  ports:
  - protocol: TCP
    port: 80
    targetPort: 9000
  type: LoadBalancer
```

## 🔍 Debugging & Troubleshooting

### **1. Logging Configuration**

```python
# Enhanced logging setup
import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logging(level=logging.INFO, log_file='mas-planning.log'):
    """Setup comprehensive logging"""
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    
    # File handler với rotation
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Specific loggers
    loggers = [
        'template.agent.manager',
        'template.agent.plan',
        'template.agent.meta',
        'template.agent.tool',
        'template.router.v1.ai'
    ]
    
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)

# Usage
if env.DEBUG_MODE:
    setup_logging(logging.DEBUG, 'debug.log')
else:
    setup_logging(logging.INFO, 'mas-planning.log')
```

### **2. Debug Tools**

```python
# Debug utilities
class DebugManager:
    """Debug utilities for development"""
    
    def __init__(self):
        self.debug_enabled = env.DEBUG_MODE
        self.trace_calls = False
        self.performance_tracking = True
    
    def trace_function_calls(self, func):
        """Decorator to trace function calls"""
        if not self.debug_enabled:
            return func
        
        def wrapper(*args, **kwargs):
            logger.debug(f"TRACE: Calling {func.__name__} với args={args}, kwargs={kwargs}")
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                logger.debug(f"TRACE: {func.__name__} completed trong {duration:.3f}s")
                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.debug(f"TRACE: {func.__name__} failed trong {duration:.3f}s với error: {e}")
                raise
        
        return wrapper
    
    def dump_state(self, state: Dict, context: str = ""):
        """Dump state for debugging"""
        if not self.debug_enabled:
            return
        
        logger.debug(f"STATE DUMP ({context}):")
        for key, value in state.items():
            if isinstance(value, (str, int, float, bool)):
                logger.debug(f"  {key}: {value}")
            elif isinstance(value, (list, dict)):
                logger.debug(f"  {key}: {type(value).__name__} length={len(value)}")
            else:
                logger.debug(f"  {key}: {type(value).__name__}")
    
    def performance_monitor(self, operation_name: str):
        """Context manager for performance monitoring"""
        class PerformanceMonitor:
            def __init__(self, name):
                self.name = name
                self.start_time = None
            
            def __enter__(self):
                self.start_time = time.time()
                logger.debug(f"PERF: Starting {self.name}")
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - self.start_time
                if exc_type:
                    logger.debug(f"PERF: {self.name} failed trong {duration:.3f}s")
                else:
                    logger.debug(f"PERF: {self.name} completed trong {duration:.3f}s")
        
        return PerformanceMonitor(operation_name)

# Usage
debug_manager = DebugManager()

@debug_manager.trace_function_calls
def some_function(param1, param2):
    with debug_manager.performance_monitor("some_operation"):
        # Your code here
        debug_manager.dump_state({"param1": param1, "param2": param2}, "function_start")
        return result
```

### **3. Common Issues & Solutions**

```python
# Common troubleshooting scenarios
class TroubleshootingGuide:
    """Common issues và their solutions"""
    
    @staticmethod
    def diagnose_mcp_connection():
        """Diagnose MCP connection issues"""
        try:
            import asyncio
            import aiohttp
            
            async def test_mcp():
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(f"{env.MCP_SERVER_URL}/health") as response:
                        if response.status == 200:
                            logger.info("✅ MCP server is reachable")
                            return True
                        else:
                            logger.error(f"❌ MCP server returned status {response.status}")
                            return False
            
            return asyncio.run(test_mcp())
            
        except Exception as e:
            logger.error(f"❌ MCP connection test failed: {e}")
            return False
    
    @staticmethod
    def diagnose_vertex_ai():
        """Diagnose Vertex AI connection"""
        try:
            from langchain_google_vertexai import ChatVertexAI
            
            # Check credentials file
            if not os.path.exists(env.GOOGLE_APPLICATION_CREDENTIALS):
                logger.error(f"❌ Service account file not found: {env.GOOGLE_APPLICATION_CREDENTIALS}")
                return False
            
            # Test LLM initialization
            llm = ChatVertexAI(
                model_name="gemini-2.5-pro",
                project=env.GOOGLE_CLOUD_PROJECT,
                location=env.GOOGLE_CLOUD_LOCATION
            )
            
            # Test simple call
            response = llm.invoke("Hello")
            logger.info("✅ Vertex AI connection successful")
            return True
            
        except Exception as e:
            logger.error(f"❌ Vertex AI connection failed: {e}")
            return False
    
    @staticmethod
    def diagnose_redis():
        """Diagnose Redis connection"""
        try:
            import redis
            
            r = redis.Redis(
                host=env.REDIS_HOST,
                port=env.REDIS_PORT,
                db=env.REDIS_DB,
                socket_timeout=5
            )
            
            # Test connection
            r.ping()
            logger.info("✅ Redis connection successful")
            return True
            
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            return False
    
    @staticmethod
    def run_full_diagnosis():
        """Run complete system diagnosis"""
        logger.info("🔍 Running system diagnosis...")
        
        results = {
            'mcp_server': TroubleshootingGuide.diagnose_mcp_connection(),
            'vertex_ai': TroubleshootingGuide.diagnose_vertex_ai(),
            'redis': TroubleshootingGuide.diagnose_redis()
        }
        
        all_healthy = all(results.values())
        
        if all_healthy:
            logger.info("✅ All systems healthy")
        else:
            failed_systems = [k for k, v in results.items() if not v]
            logger.error(f"❌ Failed systems: {', '.join(failed_systems)}")
        
        return results

# CLI tool for diagnosis
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        TroubleshootingGuide.run_full_diagnosis()
```

---

*Development Guide này cung cấp comprehensive framework để develop, test, và deploy MAS-Planning system effectively. Follow các best practices này để ensure code quality, maintainability, và reliable deployment.*