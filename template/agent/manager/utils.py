"""
Utility functions for Manager Agent
"""
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional, List
import logging
from termcolor import colored

logger = logging.getLogger(__name__)


def extract_manager_response(content: str) -> Dict[str, Any]:
    """
    Extract structured data from Manager Agent's LLM response
    
    Args:
        content: Raw LLM response content
        
    Returns:
        Dict containing extracted data
    """
    result = {
        'reasoning': '',
        'agent_type': 'direct',
        'confidence': 0.5,
        'explanation': '',
        'direct_answer': ''
    }
    
    try:
        # Extract reasoning
        reasoning_match = re.search(r'<reasoning>(.*?)</reasoning>', content, re.DOTALL)
        if reasoning_match:
            result['reasoning'] = reasoning_match.group(1).strip()
        
        # Extract agent_type
        agent_type_match = re.search(r'<agent_type>(.*?)</agent_type>', content, re.DOTALL)
        if agent_type_match:
            agent_type = agent_type_match.group(1).strip().lower()
            if agent_type in ['plan', 'meta', 'tool', 'direct']:
                result['agent_type'] = agent_type
        
        # Extract confidence
        confidence_match = re.search(r'<confidence>(.*?)</confidence>', content, re.DOTALL)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1).strip())
                result['confidence'] = max(0.0, min(1.0, confidence))  # Clamp to [0,1]
            except ValueError:
                logger.warning(colored("Could not parse confidence score, using default 0.5"), 'yellow')
        
        # Extract explanation
        explanation_match = re.search(r'<explanation>(.*?)</explanation>', content, re.DOTALL)
        if explanation_match:
            result['explanation'] = explanation_match.group(1).strip()
        
        # Extract direct_answer if present
        direct_answer_match = re.search(r'<direct_answer>(.*?)</direct_answer>', content, re.DOTALL)
        if direct_answer_match:
            result['direct_answer'] = direct_answer_match.group(1).strip()
            
    except Exception as e:
        logger.error(f"Error extracting manager response: {str(e)}")
        # Return default values if extraction fails
        result['explanation'] = "Error parsing response"
    
    return result


def classify_query_type(query: str) -> str:
    """
    Classify user query into categories for routing assistance
    
    Args:
        query: User input query
        
    Returns:
        Query type classification
    """
    query_lower = query.lower().strip()
    
    # Selection keywords (check first - most specific)
    selection_keywords = [
        'plan 1', 'plan 2', 'plan 3', 'option 1', 'option 2', 'option 3',
        'choose', 'select', 'pick', 'go with'
    ]
    
    # Check for exact plan selection patterns
    if (query_lower in ['1', '2', '3'] or 
        any(keyword in query_lower for keyword in selection_keywords)):
        return 'selection'
    
    # Planning keywords
    planning_keywords = [
        'plan', 'create', 'setup', 'automate', 'automation', 'configure',
        'install', 'design', 'build', 'smart home', 'schedule'
    ]
    
    # Execution keywords  
    execution_keywords = [
        'turn on', 'turn off', 'set', 'control', 'adjust', 'change',
        'start', 'stop', 'open', 'close', 'increase', 'decrease'
    ]
    
    # Information keywords
    info_keywords = [
        'what is', 'how does', 'explain', 'help', 'info', 'information',
        'tell me', 'describe', 'what can you do'
    ]
    
    # Check for planning keywords
    if any(keyword in query_lower for keyword in planning_keywords):
        return 'planning'
        
    # Check for execution keywords
    if any(keyword in query_lower for keyword in execution_keywords):
        return 'execution'
        
    # Check for information keywords
    if any(keyword in query_lower for keyword in info_keywords):
        return 'information'
    
    # Default classification
    return 'general'


def format_final_response(
    agent_result: Dict[str, Any], 
    agent_type: str, 
    query: str,
    language_code: str = "en-US"
) -> str:
    """
    Format the final response from delegated agent with optimization:
    - Fast processing (<100ms target)
    - Length limit (max 1000 chars)
    - Language-aware
    - Remove technical details
    
    Args:
        agent_result: Result from the delegated agent
        agent_type: Type of agent that handled the request
        query: Original user query
        language_code: Language code from client (e.g., 'vi-VN', 'en-US')
        
    Returns:
        Optimized final response
    """
    # Determine if Vietnamese based on language_code from client
    is_vietnamese = language_code.startswith('vi')
    
    if agent_type == 'direct':
        # Try 'output' first (for fast-path), then 'direct_answer' (legacy)
        raw_output = agent_result.get('output') or agent_result.get('direct_answer', '')
        if not raw_output:
            return 'Xin lỗi, tôi không thể xử lý yêu cầu của bạn.' if is_vietnamese else 'I apologize, but I could not process your request.'
        return _optimize_output(raw_output, is_vietnamese)
    
    # Format based on agent type
    if agent_type == 'plan':
        return format_plan_response(agent_result, query, language_code)
    elif agent_type == 'tool':
        return format_tool_response(agent_result, query, language_code)
    else:
        raw_output = str(agent_result.get('output', ''))
        if not raw_output:
            return 'Yêu cầu đã được xử lý thành công.' if is_vietnamese else 'Request processed successfully.'
        return _optimize_output(raw_output, is_vietnamese)


def _optimize_output(text: str, is_vietnamese: bool = True) -> str:
    """
    Fast output optimization (<100ms target)
    - Remove technical details
    - Limit length
    - Ensure proper language
    """
    if not text or len(text) < 3:
        return 'Đã xử lý xong.' if is_vietnamese else 'Processed.'
    
    # Quick length check
    MAX_LENGTH = 1000
    if len(text) <= MAX_LENGTH:
        return text.strip()
    
    # Need to truncate - try to do it smartly
    truncated = text[:MAX_LENGTH]
    
    # Find last sentence boundary
    last_period = max(
        truncated.rfind('.'),
        truncated.rfind('!'),
        truncated.rfind('?'),
        truncated.rfind('。')  # Chinese/Japanese period
    )
    
    if last_period > MAX_LENGTH * 0.7:  # Found good breaking point
        return truncated[:last_period + 1].strip()
    
    # No good breaking point, just cut and add ellipsis
    return truncated.rstrip() + '...'



def format_plan_response(agent_result: Dict[str, Any], query: str, language_code: str = "en-US") -> str:
    """Format Plan Agent response based on user's language preference"""
    output = agent_result.get('output', '')
    
    # Determine language
    is_vietnamese = language_code.startswith('vi')
    
    if 'waiting_for_selection' in output:
        # Plan options available, format them nicely
        plan_options = agent_result.get('plan_options', {})
        if plan_options:
            # Multilingual text
            if is_vietnamese:
                response = f"🏠 **Kế Hoạch Tự Động Hóa Nhà Thông Minh**\n\n"
                response += f"Tôi đã tạo 2 kế hoạch tối ưu cho yêu cầu của bạn: '{query}'\n\n"
            else:
                response = f"🏠 **Smart Home Automation Plans**\n\n"
                response += f"I've created 2 optimized plans for your request: '{query}'\n\n"
            
            # Optimized Plan
            if plan_options.get('optimized_plan'):
                if is_vietnamese:
                    response += "🥇 **Kế Hoạch 1: Tối Ưu (Bảo Mật + Tiện Lợi)**\n"
                else:
                    response += "🥇 **Plan 1: Optimized (Security + Convenience)**\n"
                    
                for i, task in enumerate(plan_options['optimized_plan'], 1):
                    response += f"   {i}. {task}\n"
                response += "\n"
            
            # Conservative Plan
            if plan_options.get('conservative_plan'):
                if is_vietnamese:
                    response += "🥈 **Kế Hoạch 2: Bảo Thủ (Tiết Kiệm + Bảo Mật)**\n"
                else:
                    response += "🥈 **Plan 2: Conservative (Energy + Security)**\n"
                    
                for i, task in enumerate(plan_options['conservative_plan'], 1):
                    response += f"   {i}. {task}\n"
                response += "\n"
            
            # Selection instruction
            if is_vietnamese:
                response += "Vui lòng chọn kế hoạch bạn muốn thực hiện bằng cách nói 'Kế hoạch 1' hoặc 'Kế hoạch 2'."
            else:
                response += "Please select which plan you'd like to implement by saying 'Plan 1' or 'Plan 2'."
                
            return response
    
    return output


def format_tool_response(agent_result: Dict[str, Any], query: str, language_code: str = "en-US") -> str:
    """
    Format Tool Agent response with optimization:
    - Remove technical details
    - Limit length to 1000 chars
    - Ensure proper language
    - Clean and user-friendly output
    - Handle API errors gracefully
    - Translate Vietnamese messages if user selected English
    
    Args:
        agent_result: Result from the Tool Agent
        query: Original user query
        language_code: Language code from client (e.g., 'vi-VN', 'en-US')
    """
    import re
    
    output = agent_result.get('output', '')
    route = agent_result.get('route', '')
    
    if not output:
        return "✅ Yêu cầu đã được xử lý thành công." if language_code.startswith('vi') else "✅ Request processed successfully."
    
    # Determine if Vietnamese based on language_code from client
    is_vietnamese = language_code.startswith('vi')
    
    # First, check for specific API errors and provide user-friendly messages
    output_lower = output.lower()
    
    # Handle 500 Internal Server Error
    if 'server error' in output_lower or '500' in output_lower or 'internal server error' in output_lower:
        if is_vietnamese:
            return "❌ Không thể kết nối với thiết bị. Vui lòng kiểm tra kết nối mạng và thử lại."
        else:
            return "❌ Unable to connect to device. Please check network connection and try again."
    
    # Handle 401 Unauthorized
    if '401' in output_lower or 'unauthorized' in output_lower or 'authentication' in output_lower:
        if is_vietnamese:
            return "🔐 Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."
        else:
            return "🔐 Session expired. Please login again."
    
    # Handle 404 Not Found
    if '404' in output_lower or 'not found' in output_lower:
        if is_vietnamese:
            return "❓ Không tìm thấy thiết bị hoặc phòng được yêu cầu."
        else:
            return "❓ Requested device or room not found."
    
    # Handle timeout errors
    if 'timeout' in output_lower or 'timed out' in output_lower:
        if is_vietnamese:
            return "⏱️ Yêu cầu quá lâu không phản hồi. Vui lòng thử lại."
        else:
            return "⏱️ Request timed out. Please try again."
    
    # Handle connection errors
    if 'connection' in output_lower and 'error' in output_lower:
        if is_vietnamese:
            return "🔌 Lỗi kết nối. Vui lòng kiểm tra mạng và thử lại."
        else:
            return "🔌 Connection error. Please check network and try again."
    
    # Remove technical debugging info
    # Remove lines starting with technical markers
    technical_markers = [
        'DEBUG', 'INFO', 'WARNING', 'ERROR',
        'Traceback', 'File "', 'line ',
        'Exception:', 'Error:', 'Failed:',
        '---', 'Debug Info:', '*Debug',
        'Routed to', 'confidence:',
        'Server Error for url:', 'http://', 'https://',
        'status_code', 'response.json', 'response.text',
        'Request failed', 'API Error', 'Stack trace',
        '<Response', '<!DOCTYPE', '<html>', '<head>',
        'at line', 'in function', 'raised exception',
    ]
    
    lines = output.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        # Skip empty lines
        if not line:
            continue
        # Skip technical lines
        if any(marker.lower() in line.lower() for marker in technical_markers):
            continue
        # Skip lines with only special characters
        if all(c in '=-*#|[]{}()<>/' for c in line):
            continue
        # Skip lines that look like code/JSON
        if line.startswith(('{', '[', '}', ']', '"', "'")):
            continue
        
        cleaned_lines.append(line)
    
    # Rejoin cleaned lines
    cleaned_output = ' '.join(cleaned_lines)
    
    # Remove multiple spaces
    cleaned_output = re.sub(r'\s+', ' ', cleaned_output).strip()
    
    # Remove technical phrases that might have slipped through
    technical_phrases = [
        r'API call failed',
        r'Request to.*failed',
        r'Error code \d+',
        r'Status: \d+',
        r'\d{3} error',
    ]
    for phrase in technical_phrases:
        cleaned_output = re.sub(phrase, '', cleaned_output, flags=re.IGNORECASE)
    
    cleaned_output = re.sub(r'\s+', ' ', cleaned_output).strip()
    
    # TRANSLATION LAYER: Translate Vietnamese API messages to English if needed
    if not is_vietnamese and cleaned_output:
        # Common Vietnamese -> English translations for API messages
        translations = {
            # Device status
            "Không thể kết nối": "Cannot connect",
            "Đang kết nối": "Connected",
            "bật": "on",
            "tắt": "off",
            
            # Error messages
            "Không tìm thấy thông tin nhà": "Home information not found",
            "Không tìm thấy thiết bị": "Device not found",
            "Không tìm thấy phòng": "Room not found",
            "Không tìm thấy thông tin": "Information not found",
            "Lỗi khi lấy danh sách thiết bị": "Error retrieving device list",
            "Lỗi khi lấy dữ liệu": "Error retrieving data",
            "Lỗi khi gửi lệnh": "Error sending command",
            "Lỗi kết nối": "Connection error",
            
            # Success messages
            "Yêu cầu đã được xử lý thành công": "Request processed successfully",
            "Đã xử lý xong": "Processed",
            "Thành công": "Success",
            "Hoàn thành": "Completed",
            
            # Action messages
            "Tất cả thiết bị đã được": "All devices have been",
            "thành công": "successfully",
            "Đang bật": "Turning on",
            "Đang tắt": "Turning off",
            
            # Device control
            "điều hòa": "air conditioner",
            "điều khiển": "control",
            "thiết bị": "device",
            "phòng": "room",
        }
        
        # Apply translations
        for vi_text, en_text in translations.items():
            cleaned_output = cleaned_output.replace(vi_text, en_text)
    
    # Limit length (max 800 chars, leave room for formatting)
    MAX_LENGTH = 800
    if len(cleaned_output) > MAX_LENGTH:
        # Try to cut at sentence boundary
        truncated = cleaned_output[:MAX_LENGTH]
        last_period = max(
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?')
        )
        
        if last_period > MAX_LENGTH * 0.7:  # If we found a good breaking point
            cleaned_output = truncated[:last_period + 1]
        else:
            cleaned_output = truncated[:MAX_LENGTH] + '...'
    
    # If output is too short or empty after cleaning, provide fallback
    if len(cleaned_output) < 5:
        # Try to infer from original output
        if any(word in output_lower for word in ['success', 'completed', 'done', 'thành công']):
            if is_vietnamese:
                cleaned_output = "✅ Yêu cầu đã được thực hiện thành công."
            else:
                cleaned_output = "✅ Request completed successfully."
        elif any(word in output_lower for word in ['error', 'failed', 'unsuccessful', 'lỗi']):
            if is_vietnamese:
                cleaned_output = "❌ Đã xảy ra lỗi khi thực hiện yêu cầu. Vui lòng thử lại."
            else:
                cleaned_output = "❌ An error occurred. Please try again."
        else:
            if is_vietnamese:
                cleaned_output = "✅ Yêu cầu đã được xử lý."
            else:
                cleaned_output = "✅ Request processed."
    
    # Add emoji prefix based on success/failure (if not already present)
    if not cleaned_output.startswith(('✅', '❌', '⚠️', '🔧', '💡', '🏠', '🔐', '❓', '⏱️', '🔌')):
        if any(word in cleaned_output.lower() for word in ['thành công', 'success', 'completed', 'done']):
            cleaned_output = f"✅ {cleaned_output}"
        elif any(word in cleaned_output.lower() for word in ['lỗi', 'error', 'failed', 'unsuccessful']):
            cleaned_output = f"❌ {cleaned_output}"
    
    return cleaned_output


def extract_plan_selection(query: str) -> Optional[int]:
    """
    Extract plan selection number from user query (supports Vietnamese and English)
    
    Args:
        query: User input
        
    Returns:
        Plan number (1 or 2) or None
    """
    query_lower = query.lower().strip()
    
    # Check for explicit plan numbers (English)
    if 'plan 1' in query_lower or query_lower == '1':
        return 1
    elif 'plan 2' in query_lower or query_lower == '2':
        return 2
    
    # Check for Vietnamese plan selections
    if 'kế hoạch 1' in query_lower or 'ke hoach 1' in query_lower:
        return 1
    elif 'kế hoạch 2' in query_lower or 'ke hoach 2' in query_lower:
        return 2
    
    # Check for alternative formats (English)
    if 'option 1' in query_lower or 'first' in query_lower:
        return 1
    elif 'option 2' in query_lower or 'second' in query_lower:
        return 2
    
    # Check for Vietnamese alternatives
    if 'lựa chọn 1' in query_lower or 'lua chon 1' in query_lower or 'thứ nhất' in query_lower or 'thu nhat' in query_lower:
        return 1
    elif 'lựa chọn 2' in query_lower or 'lua chon 2' in query_lower or 'thứ hai' in query_lower or 'thu hai' in query_lower:
        return 2
    
    # Check for plan types (English)
    if 'optimized' in query_lower:
        return 1
    elif 'conservative' in query_lower:
        return 2
    
    # Check for plan types (Vietnamese)
    if 'tối ưu' in query_lower or 'toi uu' in query_lower:
        return 1
    elif 'bảo thủ' in query_lower or 'bao thu' in query_lower or 'tiết kiệm' in query_lower or 'tiet kiem' in query_lower:
        return 2
    
    return None


def validate_agent_result(agent_result: Any, agent_type: str) -> bool:
    """
    Validate the result from a delegated agent
    
    Args:
        agent_result: Result from agent
        agent_type: Type of agent
        
    Returns:
        True if result is valid
    """
    if not agent_result:
        return False
    
    if not isinstance(agent_result, dict):
        return False
    
    # Check for required fields based on agent type
    if agent_type == 'plan':
        return 'output' in agent_result or 'plan_options' in agent_result
    elif agent_type == 'meta':
        return 'output' in agent_result
    elif agent_type == 'tool':
        return 'output' in agent_result
    
    return True


def get_agent_capabilities() -> Dict[str, List[str]]:
    """
    Get capabilities of each agent for routing decisions
    
    Returns:
        Dict mapping agent types to their capabilities
    """
    return {
        'plan': [
            'Create smart home automation plans',
            'Generate 3 priority-based plan options',
            'Handle plan selection and execution',
            'Coordinate complex multi-step workflows'
        ],
        'meta': [
            'Complex reasoning and analysis',
            'Meta-cognitive task handling',
            'Strategic planning decisions',
            'Abstract problem solving'
        ],
        'tool': [
            'Device control operations',
            'MCP tool execution',
            'Smart home device management',
            'Real-time system interactions'
        ],
        'direct': [
            'Simple information queries',
            'Basic question answering',
            'General help and guidance'
        ]
    }