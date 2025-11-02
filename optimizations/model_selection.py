"""
Gemini Flash Model Configuration
Switch từ gemini-2.5-pro → gemini-2.5-flash để giảm latency
"""
from typing import Optional
import os


class ModelSelector:
    """
    Smart model selection based on query complexity
    """
    
    # Model configurations
    MODELS = {
        'flash': {
            'name': 'gemini-2.5-flash',
            'temperature': 0.1,
            'max_tokens': 512,
            'top_p': 0.8,
            'latency': 'low',      # ~2-3s per call
            'cost': 'low',
            'quality': 'good',
        },
        'pro': {
            'name': 'gemini-2.5-pro',
            'temperature': 0.2,
            'max_tokens': 1024,
            'top_p': 0.95,
            'latency': 'high',     # ~6-8s per call
            'cost': 'high',
            'quality': 'excellent',
        }
    }
    
    # Simple query keywords
    SIMPLE_KEYWORDS = [
        'turn on', 'turn off',
        'open', 'close',
        'activate', 'deactivate',
        'switch', 'toggle',
        'set to',
    ]
    
    # Complex query indicators
    COMPLEX_INDICATORS = [
        'create plan', 'make routine',
        'schedule', 'automation',
        'if', 'when', 'then',
        'multiple', 'all rooms',
        'except', 'unless',
    ]
    
    @classmethod
    def select_model(cls, query: str, force_model: Optional[str] = None) -> dict:
        """
        Select appropriate model based on query complexity
        
        Args:
            query: User query
            force_model: Force use of specific model ('flash' or 'pro')
        
        Returns:
            Model configuration dict
        """
        # Check environment override
        env_model = os.getenv('FORCE_MODEL')
        if env_model:
            force_model = env_model
        
        if force_model:
            return cls.MODELS.get(force_model, cls.MODELS['flash'])
        
        query_lower = query.lower()
        
        # Check for complex indicators
        is_complex = any(
            indicator in query_lower 
            for indicator in cls.COMPLEX_INDICATORS
        )
        
        if is_complex:
            return cls.MODELS['pro']
        
        # Check for simple keywords
        is_simple = any(
            keyword in query_lower 
            for keyword in cls.SIMPLE_KEYWORDS
        )
        
        if is_simple:
            return cls.MODELS['flash']
        
        # Default to flash for better latency
        return cls.MODELS['flash']
    
    @classmethod
    def get_llm_config(cls, query: str, force_model: Optional[str] = None) -> dict:
        """
        Get LLM configuration for ChatVertexAI
        
        Usage:
            config = ModelSelector.get_llm_config(user_query)
            llm = ChatVertexAI(**config)
        """
        model_config = cls.select_model(query, force_model)
        
        return {
            'model_name': model_config['name'],
            'temperature': model_config['temperature'],
            'max_tokens': model_config['max_tokens'],
            'top_p': model_config['top_p'],
        }


# ============================================================
# Integration Examples
# ============================================================

def enhanced_manager_init(self, query: str):
    """
    Enhanced ManagerAgent with smart model selection
    
    Replace in ManagerAgent.__init__:
    """
    from langchain_google_vertexai import ChatVertexAI
    
    # Smart model selection
    llm_config = ModelSelector.get_llm_config(query)
    
    self.llm = ChatVertexAI(
        **llm_config,
        project=env.GOOGLE_CLOUD_PROJECT,
        location=env.GOOGLE_CLOUD_LOCATION
    )


def enhanced_tool_agent_init(self, query: str):
    """
    Enhanced ToolAgent with smart model selection
    
    Add to ToolAgent.init_async():
    """
    from langchain_google_vertexai import ChatVertexAI
    
    # For Tool Agent, almost always use flash for speed
    force_flash = os.getenv('TOOL_AGENT_FORCE_FLASH', 'true').lower() == 'true'
    
    if force_flash:
        llm_config = ModelSelector.MODELS['flash']
    else:
        llm_config = ModelSelector.get_llm_config(query)
    
    base_llm = ChatVertexAI(
        model_name=llm_config['name'],
        temperature=llm_config['temperature'],
        max_tokens=llm_config['max_tokens'],
        top_p=llm_config['top_p'],
        project=env.GOOGLE_CLOUD_PROJECT,
        location=env.GOOGLE_CLOUD_LOCATION,
    )


# ============================================================
# Environment Configuration
# ============================================================

"""
Add to .env or docker-compose.yml:

# Force specific model globally
FORCE_MODEL=flash  # or 'pro'

# Force flash for Tool Agent only
TOOL_AGENT_FORCE_FLASH=true

# Model settings
FLASH_TEMPERATURE=0.1
FLASH_MAX_TOKENS=512
PRO_TEMPERATURE=0.2
PRO_MAX_TOKENS=1024
"""


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    test_queries = [
        "Turn on the living room lights",
        "Turn off all devices",
        "Create a morning automation plan",
        "Set AC to 24 degrees",
        "If motion detected, turn on lights",
        "Open the garage door",
    ]
    
    print("=" * 60)
    print("Model Selection Test")
    print("=" * 60)
    
    for query in test_queries:
        config = ModelSelector.select_model(query)
        llm_config = ModelSelector.get_llm_config(query)
        
        print(f"\n📝 Query: {query}")
        print(f"   🤖 Model: {config['name']}")
        print(f"   ⚡ Latency: {config['latency']}")
        print(f"   💰 Cost: {config['cost']}")
        print(f"   ⭐ Quality: {config['quality']}")
        print(f"   ⚙️  Config: {llm_config}")
    
    print("\n" + "=" * 60)
    
    # Test forced model
    print("\n🔒 Testing forced model (flash):")
    config = ModelSelector.select_model(
        "Create a complex automation plan",
        force_model='flash'
    )
    print(f"   Model: {config['name']} (forced)")
