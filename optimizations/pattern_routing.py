"""
Pattern-Based Routing Optimization
Giảm Manager routing time từ 8.5s → 0.1s cho simple commands
"""
import re
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class PatternRouter:
    """Fast pattern-based routing for common commands"""
    
    # Device control patterns
    DEVICE_CONTROL_PATTERNS = [
        (r'\b(turn|switch)\s+(on|off)\b', 'tool', 0.95),
        (r'\b(open|close)\s+\w+', 'tool', 0.90),
        (r'\b(activate|deactivate)\b', 'tool', 0.90),
        (r'\bset\s+\w+\s+to\s+\d+', 'tool', 0.85),
        (r'\b(dim|brighten)\b', 'tool', 0.85),
        (r'\b(increase|decrease)\s+(temperature|brightness)', 'tool', 0.85),
    ]
    
    # Plan creation patterns
    PLAN_PATTERNS = [
        (r'\bcreate\s+(a\s+)?plan\b', 'plan', 0.95),
        (r'\bmake\s+(a\s+)?routine\b', 'plan', 0.90),
        (r'\bschedule\s+\w+', 'plan', 0.90),
        (r'\bplan\s+for\b', 'plan', 0.85),
        (r'\bautomation\s+for\b', 'plan', 0.85),
    ]
    
    # Information/help patterns
    INFO_PATTERNS = [
        (r'\b(what|how|when|where|why)\b', 'meta', 0.70),
        (r'\b(tell|show)\s+me\b', 'meta', 0.70),
        (r'\b(list|get)\s+(all\s+)?devices', 'meta', 0.80),
        (r'\bstatus\s+of\b', 'meta', 0.75),
    ]
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.patterns = (
            self.DEVICE_CONTROL_PATTERNS +
            self.PLAN_PATTERNS +
            self.INFO_PATTERNS
        )
    
    def quick_route(self, user_input: str) -> Optional[Tuple[str, float, str]]:
        """
        Fast pattern matching routing
        
        Returns:
            (agent_type, confidence, reasoning) if matched, else None
        """
        input_lower = user_input.lower()
        
        for pattern, agent_type, confidence in self.patterns:
            if re.search(pattern, input_lower, re.IGNORECASE):
                reasoning = f"Pattern match: '{pattern}' → {agent_type}"
                
                if self.verbose:
                    logger.info(f"⚡ Quick route: {agent_type} (confidence: {confidence:.2f})")
                    logger.info(f"📝 Pattern: {pattern}")
                
                return (agent_type, confidence, reasoning)
        
        # No pattern match
        return None
    
    def should_use_llm(self, user_input: str, threshold: float = 0.80) -> bool:
        """
        Determine if we should fall back to LLM routing
        
        Args:
            user_input: User query
            threshold: Confidence threshold for pattern routing
        
        Returns:
            True if should use LLM, False if pattern routing is confident enough
        """
        result = self.quick_route(user_input)
        
        if result is None:
            # No pattern match → use LLM
            return True
        
        agent_type, confidence, reasoning = result
        
        if confidence < threshold:
            # Low confidence → use LLM
            if self.verbose:
                logger.info(f"⚠️ Low confidence ({confidence:.2f}), falling back to LLM")
            return True
        
        # High confidence → use pattern routing
        return False


# ============================================================
# Integration Example
# ============================================================

def enhanced_analyze_query(self, state):
    """
    Enhanced version with pattern routing
    
    Add this to ManagerAgent class
    """
    if not hasattr(self, '_pattern_router'):
        self._pattern_router = PatternRouter(verbose=self.verbose)
    
    user_input = state.get('input', '')
    
    # Try quick pattern routing first
    quick_result = self._pattern_router.quick_route(user_input)
    
    if quick_result and quick_result[1] >= 0.85:  # High confidence
        agent_type, confidence, reasoning = quick_result
        
        if self.verbose:
            logger.info(f"🎯 Pattern routing: {agent_type} (skipped LLM)")
        
        return {
            **state,
            'agent_type': agent_type,
            'confidence': confidence,
            'reasoning': reasoning,
            'method': 'pattern_matching'
        }
    
    # Fall back to LLM for complex/ambiguous queries
    if self.verbose:
        logger.info(f"🔍 Using LLM analysis (no confident pattern match)")
    
    return self.llm_analyze_query(state)


# ============================================================
# Testing
# ============================================================

if __name__ == "__main__":
    router = PatternRouter(verbose=True)
    
    test_cases = [
        "Turn on the living room lights",
        "Turn off bedroom fan",
        "Create a morning routine plan",
        "What's the temperature in the bedroom?",
        "Set AC to 24 degrees",
        "Open the garage door",
        "Tell me about my devices",
        "Activate security system",
    ]
    
    print("=" * 60)
    print("Pattern Routing Test")
    print("=" * 60)
    
    for query in test_cases:
        print(f"\n📝 Query: {query}")
        result = router.quick_route(query)
        
        if result:
            agent_type, confidence, reasoning = result
            print(f"   ✅ Route: {agent_type} (confidence: {confidence:.2f})")
            print(f"   📋 Reason: {reasoning}")
        else:
            print(f"   ❌ No pattern match → Use LLM")
    
    print("\n" + "=" * 60)
