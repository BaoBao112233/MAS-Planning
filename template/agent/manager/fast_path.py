"""
Fast-path Intent Classifier
Phân loại intent và routing cho các loại query khác nhau:
- device_control: Điều khiển thiết bị (routing: Tool Agent → Manager)
- show_device_status: Hiển thị trạng thái thiết bị (routing: Manager only)
- planning: Tạo kế hoạch tự động hóa (routing: Manager → Plan Agent → Tool Agent → Manager)
- unknown: Query không xác định (routing: Manager only)

Performance target: Sub-second processing for all paths
"""

import re
import logging
import hashlib
import time
import json
from typing import Optional, Dict, Tuple, List, Any
from functools import lru_cache
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class IntentClass(Enum):
    """Các loại intent classification"""
    DEVICE_CONTROL = "device_control"
    SHOW_DEVICE_STATUS = "show_device_status"
    PLANNING = "planning"
    UNKNOWN = "unknown"


class ExecutionPath(Enum):
    """Execution paths cho các loại intent"""
    TOOL_THEN_MANAGER = "tool_then_manager"  # device_control: Tool → Manager
    MANAGER_ONLY = "manager_only"  # show_device_status, unknown: Manager only
    FULL_PLANNING = "full_planning"  # planning: Manager → Plan → Tool → Manager


@dataclass
@dataclass
class ClassificationResult:
    """Kết quả phân loại intent"""
    intent: IntentClass
    confidence: float
    execution_path: ExecutionPath
    method: str  # 'pattern' hoặc 'ml'
    extracted_params: Dict[str, Any]
    reasoning: str
    
    def to_dict(self) -> Dict:
        return {
            'intent': self.intent.value,
            'confidence': self.confidence,
            'execution_path': self.execution_path.value,
            'method': self.method,
            'extracted_params': self.extracted_params,
            'reasoning': self.reasoning
        }


class FastPathClassifier:
    """
    Fast-path intent classification với 4 loại chính:
    1. device_control: Điều khiển thiết bị trực tiếp
    2. show_device_status: Hiển thị thông tin/trạng thái thiết bị
    3. planning: Tạo automation plan
    4. unknown: Không xác định
    
    Target processing time: <1 second cho tất cả paths
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._device_cache = {}  # Simple in-memory cache
        self._cache_ttl = 60  # 60 seconds
        self._cache_timestamp = {}
        
        # Comprehensive patterns for all intent classes
        self.patterns = self._build_patterns()
    
    def _build_patterns(self) -> List[Dict]:
        """
        Build comprehensive pattern library for all intent classes.
        Returns list of pattern dictionaries with:
        - regex: compiled regex pattern
        - intent: intent class (device_control, show_device_status, planning, unknown)
        - confidence: base confidence score
        - description: human-readable description
        """
        patterns = []
        
        # ==========================================
        # 1. DEVICE CONTROL PATTERNS
        # Routing: Tool Agent → Manager (fast execution)
        # ==========================================
        
        # Basic ON/OFF commands - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(bật|mở|turn\s*on|open)\s+(.+?)(?:\s+(?:ở|tại|in|at)\s+(.+?))?$', re.IGNORECASE),
                'intent': IntentClass.DEVICE_CONTROL,
                'action': 'turn_on',
                'confidence': 0.95,
                'description': 'Turn on device'
            },
            {
                'regex': re.compile(r'^(tắt|đóng|turn\s*off|close)\s+(.+?)(?:\s+(?:ở|tại|in|at)\s+(.+?))?$', re.IGNORECASE),
                'intent': IntentClass.DEVICE_CONTROL,
                'action': 'turn_off',
                'confidence': 0.95,
                'description': 'Turn off device'
            },
        ])
        
        # Temperature/AC control
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set|chỉnh)\s+(?:nhiệt\s*độ|temperature|temp)?\s*(?:điều\s*hòa|ac|máy\s*lạnh)?\s*(?:ở|tại|in|at)?\s*(.+?)?\s*(?:lên|to|thành)?\s*(\d+)\s*(?:độ|°c|degrees?)?', re.IGNORECASE),
                'intent': IntentClass.DEVICE_CONTROL,
                'action': 'set_temperature',
                'confidence': 0.92,
                'description': 'Set AC temperature'
            },
            {
                'regex': re.compile(r'^(?:bật|turn\s*on)\s+(?:điều\s*hòa|ac|máy\s*lạnh)\s+(?:ở|tại|in|at)?\s*(.+?)?\s*(?:ở|at)?\s*(\d+)\s*(?:độ|°c|degrees?)?', re.IGNORECASE),
                'intent': IntentClass.DEVICE_CONTROL,
                'action': 'turn_on_ac_temp',
                'confidence': 0.93,
                'description': 'Turn on AC with temperature'
            },
        ])
        
        # Light brightness control
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set|chỉnh)\s+(?:độ\s*sáng|brightness)?\s*(?:đèn|light)?\s*(?:ở|tại|in|at)?\s*(.+?)?\s*(?:lên|to|thành)?\s*(\d+)\s*(?:%|percent)?', re.IGNORECASE),
                'intent': IntentClass.DEVICE_CONTROL,
                'action': 'set_brightness',
                'confidence': 0.91,
                'description': 'Set light brightness'
            },
        ])
        
        # Fan speed control
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set|chỉnh)\s+(?:tốc\s*độ|speed)?\s*(?:quạt|fan)?\s*(?:ở|tại|in|at)?\s*(.+?)?\s*(?:lên|to|thành)?\s*(cao|thấp|trung\s*bình|high|low|medium|auto|\d+)', re.IGNORECASE),
                'intent': IntentClass.DEVICE_CONTROL,
                'action': 'set_fan_speed',
                'confidence': 0.90,
                'description': 'Set fan speed'
            },
        ])
        
        # Multi-device control
        patterns.extend([
            {
                'regex': re.compile(r'^(bật|tắt|turn\s*on|turn\s*off)\s+(.+?)\s+(?:và|and)\s+(.+?)(?:\s+(?:ở|tại|in)\s+(.+?))?$', re.IGNORECASE),
                'intent': IntentClass.DEVICE_CONTROL,
                'action': 'multi_device',
                'confidence': 0.88,
                'description': 'Control multiple devices'
            },
        ])
        
        # ==========================================
        # 2. SHOW DEVICE STATUS PATTERNS
        # Routing: Manager only (use get_device_list)
        # ==========================================
        
        # Device status queries - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(?:trạng\s*thái|status|tình\s*trạng)\s+(?:của\s+)?(.+?)(?:\s+(?:ở|tại|in)\s+(.+?))?$', re.IGNORECASE),
                'intent': IntentClass.SHOW_DEVICE_STATUS,
                'action': 'get_status',
                'confidence': 0.94,
                'description': 'Get device status'
            },
            {
                'regex': re.compile(r'^(?:hiển\s*thị|show|list|liệt\s*kê)\s+(?:tất\s*cả\s+)?(?:thiết\s*bị|device|devices?)(?:\s+(?:ở|tại|in)\s+(.+?))?$', re.IGNORECASE),
                'intent': IntentClass.SHOW_DEVICE_STATUS,
                'action': 'list_devices',
                'confidence': 0.96,
                'description': 'Show all devices'
            },
            {
                'regex': re.compile(r'^(?:cho|give|let)\s+(?:tôi|mình|me)\s+(?:xem|see)\s+(?:tất\s*cả\s+)?(?:các\s+)?(?:thiết\s*bị|device|devices?)(?:\s+(?:ở|tại|in)\s+(.+?))?$', re.IGNORECASE),
                'intent': IntentClass.SHOW_DEVICE_STATUS,
                'action': 'list_devices',
                'confidence': 0.96,
                'description': 'Show me all devices'
            },
            {
                'regex': re.compile(r'^(?:show|display|list|hiển\s*thị)\s+(?:me\s+)?(?:all\s+)?(?:device|devices|thiết\s*bị)s?\s+(?:in|at|ở|tại)\s+(?:the\s+)?(.+?)$', re.IGNORECASE),
                'intent': IntentClass.SHOW_DEVICE_STATUS,
                'action': 'list_devices_in_room',
                'confidence': 0.96,
                'description': 'Show all devices in specific room'
            },
            {
                'regex': re.compile(r'^(?:show|display|list|hiển\s*thị)\s+(?:me\s+)?(?:all\s+)?(?:device|devices|thiết\s*bị)s?$', re.IGNORECASE),
                'intent': IntentClass.SHOW_DEVICE_STATUS,
                'action': 'list_all_devices',
                'confidence': 0.97,
                'description': 'List all devices in house'
            },
            {
                'regex': re.compile(r'^(.+?)\s+(?:có\s+)?(?:đang|is|are)\s+(?:bật|tắt|on|off)(?:\s+(?:không|\?))?$', re.IGNORECASE),
                'intent': IntentClass.SHOW_DEVICE_STATUS,
                'action': 'check_device_state',
                'confidence': 0.92,
                'description': 'Check if device is on/off'
            },
        ])
        
        # Room-specific device queries
        patterns.extend([
            {
                'regex': re.compile(r'^(?:thiết\s*bị|device|devices?)\s+(?:ở|tại|in|at)\s+(.+?)$', re.IGNORECASE),
                'intent': IntentClass.SHOW_DEVICE_STATUS,
                'action': 'devices_in_room',
                'confidence': 0.93,
                'description': 'Show devices in specific room'
            },
            {
                'regex': re.compile(r'^(?:có\s+)?(?:những\s+)?(?:thiết\s*bị|device|devices?)\s+(?:gì|nào|what)\s+(?:ở|tại|in)\s+(.+?)$', re.IGNORECASE),
                'intent': IntentClass.SHOW_DEVICE_STATUS,
                'action': 'what_devices_in_room',
                'confidence': 0.94,
                'description': 'What devices in room'
            },
        ])
        
        # ==========================================
        # 3. PLANNING PATTERNS
        # Routing: Manager → Plan Agent → Tool Agent → Manager
        # ==========================================
        
        # Automation/Plan creation - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(?:tạo|create|thiết\s*lập|setup|make)\s+(?:kế\s*hoạch|plan|automation|tự\s*động\s*hóa|routine)\s*(.*)$', re.IGNORECASE),
                'intent': IntentClass.PLANNING,
                'action': 'create_plan',
                'confidence': 0.96,
                'description': 'Create automation plan'
            },
            {
                'regex': re.compile(r'(?:tạo|create|make)\s+(?:kế\s*hoạch|plan)(?:\s+|$)', re.IGNORECASE),
                'intent': IntentClass.PLANNING,
                'action': 'create_plan',
                'confidence': 0.95,
                'description': 'Create plan anywhere in sentence'
            },
            {
                'regex': re.compile(r'^(?:lên\s*lịch|schedule|đặt\s*lịch)\s+(.+?)\s+(?:lúc|at|vào)\s+(.+?)$', re.IGNORECASE),
                'intent': IntentClass.PLANNING,
                'action': 'schedule_automation',
                'confidence': 0.93,
                'description': 'Schedule automation'
            },
            {
                'regex': re.compile(r'^(?:khi|when|nếu|if)\s+(.+?)\s+(?:thì|then)\s+(.+?)$', re.IGNORECASE),
                'intent': IntentClass.PLANNING,
                'action': 'conditional_automation',
                'confidence': 0.91,
                'description': 'Conditional automation (if-then)'
            },
            {
                'regex': re.compile(r'(?:have|có)\s+\d+\s+(?:person|people|người)', re.IGNORECASE),
                'intent': IntentClass.PLANNING,
                'action': 'person_based_automation',
                'confidence': 0.92,
                'description': 'Person-count based automation'
            },
        ])
        
        # Plan management
        patterns.extend([
            {
                'regex': re.compile(r'^(?:plan|option|kế\s*hoạch|lựa\s*chọn)\s*(\d+)$', re.IGNORECASE),
                'intent': IntentClass.PLANNING,
                'action': 'select_plan',
                'confidence': 0.95,
                'description': 'Select plan option'
            },
            {
                'regex': re.compile(r'^(?:chọn|select|choose|lấy)\s+(?:plan|kế\s*hoạch|option)\s*(\d+)$', re.IGNORECASE),
                'intent': IntentClass.PLANNING,
                'action': 'select_plan_explicit',
                'confidence': 0.97,
                'description': 'Explicit plan selection'
            },
        ])
        
        return patterns
    
    
    def classify(self, query: str, token: str = "") -> Optional[ClassificationResult]:
        """
        Fast classification của user input theo 4 intent classes.
        
        Args:
            query: User input query
            token: Authentication token
            
        Returns:
            ClassificationResult hoặc None nếu không match
            
        Intent Classes và Execution Paths:
        1. device_control → TOOL_THEN_MANAGER
           - Tool Agent thực thi trước
           - Manager phân tích kết quả và trả về user (<1s)
           
        2. show_device_status → MANAGER_ONLY
           - Manager dùng get_device_list để lấy thông tin
           - Phân tích và hiển thị thông tin cơ bản cho user (<1s)
           - Không gọi Tool Agent
           
        3. planning → FULL_PLANNING
           - Manager phân tích → Plan Agent tạo plans
           - User chọn plan → Tool Agent thực thi
           - Manager phân tích kết quả cuối cùng (<1s cho Manager analysis)
           
        4. unknown → MANAGER_ONLY
           - Manager trả lời trực tiếp (<1s)
           - Không delegate cho Agent nào khác
        """
        if not query or not isinstance(query, str):
            return None
        
        query = query.strip()
        if not query:
            return None
        
        if self.verbose:
            logger.info(f"� Fast-path: Analyzing '{query}'")
        
        # Try pattern matching first
        for pattern_def in self.patterns:
            match = pattern_def['regex'].match(query)
            if match:
                # Extract parameters from regex groups
                params = self._extract_params(match, pattern_def)
                
                # Determine execution path based on intent
                intent = pattern_def['intent']
                execution_path = self._get_execution_path(intent)
                
                # Build classification result
                result = ClassificationResult(
                    intent=intent,
                    confidence=pattern_def['confidence'],
                    execution_path=execution_path,
                    method='pattern',
                    extracted_params=params,
                    reasoning=f"Pattern match: {pattern_def['description']}"
                )
                
                if self.verbose:
                    logger.info(f"✅ Fast-path match: {pattern_def['description']}")
                    logger.info(f"   Intent: {intent.value}")
                    logger.info(f"   Execution Path: {execution_path.value}")
                    logger.info(f"   Confidence: {pattern_def['confidence']:.2f}")
                    logger.info(f"   Params: {params}")
                
                return result
        
        # No pattern match - classify as unknown with low confidence
        if self.verbose:
            logger.info(f"⚠️ Fast-path: No pattern match for '{query}' → unknown")
        
        # Return unknown classification
        return ClassificationResult(
            intent=IntentClass.UNKNOWN,
            confidence=0.5,
            execution_path=ExecutionPath.MANAGER_ONLY,
            method='fallback',
            extracted_params={},
            reasoning="No pattern match - classified as unknown"
        )
    
    def _get_execution_path(self, intent: IntentClass) -> ExecutionPath:
        """
        Determine execution path based on intent class
        
        Mapping:
        - DEVICE_CONTROL → TOOL_THEN_MANAGER
        - SHOW_DEVICE_STATUS → MANAGER_ONLY
        - PLANNING → FULL_PLANNING
        - UNKNOWN → MANAGER_ONLY
        """
        path_mapping = {
            IntentClass.DEVICE_CONTROL: ExecutionPath.TOOL_THEN_MANAGER,
            IntentClass.SHOW_DEVICE_STATUS: ExecutionPath.MANAGER_ONLY,
            IntentClass.PLANNING: ExecutionPath.FULL_PLANNING,
            IntentClass.UNKNOWN: ExecutionPath.MANAGER_ONLY
        }
        return path_mapping.get(intent, ExecutionPath.MANAGER_ONLY)
    
    def _extract_params(self, match: re.Match, pattern_def: Dict) -> Dict:
        """Extract parameters from regex match groups"""
        params = {}
        groups = match.groups()
        
        intent = pattern_def['intent']
        action = pattern_def['action']
        
        # Extract based on intent type
        if intent == IntentClass.DEVICE_CONTROL:
            # Device control parameters
            if action in ['turn_on', 'turn_off', 'turn_on_off', 'switch']:
                if len(groups) >= 2:
                    params['device_name'] = groups[1].strip() if len(groups) > 1 and groups[1] else None
                    params['room'] = groups[2].strip() if len(groups) > 2 and groups[2] else None
                    params['action_type'] = groups[0].strip() if groups[0] else action
            
            elif action in ['set_temperature', 'turn_on_ac_temp']:
                if len(groups) >= 1:
                    params['room'] = groups[0].strip() if groups[0] else None
                    # Find temperature in groups
                    for g in groups:
                        if g and g.isdigit():
                            params['temperature'] = int(g)
                            break
            
            elif action == 'set_brightness':
                if len(groups) >= 1:
                    params['device_name'] = groups[0].strip() if groups[0] else None
                    for g in groups:
                        if g and g.isdigit():
                            params['brightness'] = int(g)
                            break
            
            elif action == 'multi_device':
                if len(groups) >= 3:
                    params['action_type'] = groups[0].strip() if groups[0] else None
                    params['device_1'] = groups[1].strip() if groups[1] else None
                    params['device_2'] = groups[2].strip() if groups[2] else None
                    params['room'] = groups[3].strip() if len(groups) > 3 and groups[3] else None
        
        elif intent == IntentClass.SHOW_DEVICE_STATUS:
            # Device status query parameters
            if action in ['get_status', 'check_device_state']:
                if len(groups) >= 1:
                    params['device_name'] = groups[0].strip() if groups[0] else None
                    params['room'] = groups[1].strip() if len(groups) > 1 and groups[1] else None
            
            elif action in ['list_devices', 'list_all_devices', 'list_devices_in_room', 'devices_in_room', 'what_devices_in_room']:
                if len(groups) >= 1 and groups[0]:
                    # Strip punctuation and whitespace from room name
                    room = groups[0].strip().rstrip('.,!?;:')
                    params['room'] = room.lower()
                else:
                    params['room'] = 'all'
                params['show_all'] = (action in ['list_all_devices'])
        
        elif intent == IntentClass.PLANNING:
            # Planning parameters
            if action == 'create_plan':
                if len(groups) >= 1:
                    params['plan_description'] = groups[0].strip() if groups[0] else None
            
            elif action == 'schedule_automation':
                if len(groups) >= 2:
                    params['task'] = groups[0].strip() if groups[0] else None
                    params['time'] = groups[1].strip() if groups[1] else None
            
            elif action == 'conditional_automation':
                if len(groups) >= 2:
                    params['condition'] = groups[0].strip() if groups[0] else None
                    params['action_when_true'] = groups[1].strip() if groups[1] else None
            
            elif action in ['select_plan', 'select_plan_explicit']:
                if len(groups) >= 1 and groups[0]:
                    try:
                        params['plan_id'] = int(groups[0].strip())
                    except ValueError:
                        params['plan_id'] = 1  # Default to plan 1
        
        # Store raw groups for debugging
        params['_raw_groups'] = [g for g in groups if g]
        
        return params
    
    def _normalize_room_name(self, room_name: str) -> str:
        """
        Normalize room name for flexible matching.
        Handles case-insensitive matching and common variants.
        
        Args:
            room_name: Room name to normalize
            
        Returns:
            Normalized room name (lowercase, no extra spaces)
            
        Examples:
            "Bedroom" → "bedroom"
            "Bed room" → "bedroom"
            "Living room" → "livingroom"
            "Living Room" → "livingroom"
            "phòng ngủ" → "phòng ngủ"
        """
        if not room_name:
            return ""
        
        # Convert to lowercase and strip
        normalized = room_name.lower().strip()
        
        # Remove spaces for common English room names
        # This allows "Bed room", "bedroom", "Bedroom" to all match
        normalized = normalized.replace(" ", "")
        
        return normalized
    
    def _match_room_name(self, user_room: str, system_room: str) -> bool:
        """
        Match user-provided room name against system room name.
        Handles variants like "bedroom", "Bedroom", "Bed room", etc.
        
        Args:
            user_room: Room name from user query
            system_room: Room name from system/API
            
        Returns:
            True if rooms match
        """
        if not user_room or not system_room:
            return False
        
        # Normalize both room names
        normalized_user = self._normalize_room_name(user_room)
        normalized_system = self._normalize_room_name(system_room)
        
        # Check for exact match or partial match
        return (normalized_user == normalized_system or 
                normalized_user in normalized_system or 
                normalized_system in normalized_user)
    
    def _detect_language(self, text: str) -> str:
        """
        Detect language of input text (Vietnamese or English)
        
        Args:
            text: Input text to detect
            
        Returns:
            'vi' for Vietnamese, 'en' for English
        """
        # Vietnamese-specific characters
        vietnamese_chars = 'àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ'
        
        # Check for Vietnamese characters
        text_lower = text.lower()
        for char in vietnamese_chars:
            if char in text_lower:
                return 'vi'
        
        # Check for common Vietnamese words
        vietnamese_words = ['thiết bị', 'phòng', 'nhà', 'tất cả', 'hiển thị', 'cho tôi', 'xem']
        for word in vietnamese_words:
            if word in text_lower:
                return 'vi'
        
        # Default to English
        return 'en'
    
    def format_device_status_response(self, device_list: Dict[str, Any], 
                                     query_params: Dict[str, Any], 
                                     user_query: str = '') -> str:
        """
        Format device status response cho Manager
        Chỉ hiển thị thông tin cơ bản (không có thông tin kỹ thuật)
        Response language matches user query language
        
        Args:
            device_list: Kết quả từ get_device_list tool
            query_params: Parameters từ classification
            user_query: Original user query for language detection
            
        Returns:
            Formatted response string với thông tin cơ bản
        """
        try:
            target_room = query_params.get('room', 'all')
            show_all = query_params.get('show_all', False)
            
            # Detect language from user query
            lang = self._detect_language(user_query) if user_query else 'vi'
            
            # Language-specific messages
            messages = {
                'vi': {
                    'title': '🏠 **Danh sách thiết bị**',
                    'error_no_data': '❌ Không thể lấy thông tin thiết bị. Vui lòng thử lại.',
                    'no_devices': '📭 Không tìm thấy thiết bị nào trong hệ thống.',
                    'room_not_found': '❌ Không tìm thấy phòng \'{}\' trong hệ thống.',
                    'devices': 'Thiết bị',
                    'buttons': 'Nút điều khiển',
                    'total': 'Tổng cộng',
                    'device_unit': 'thiết bị',
                    'button_unit': 'nút điều khiển'
                },
                'en': {
                    'title': '🏠 **Device List**',
                    'error_no_data': '❌ Unable to retrieve device information. Please try again.',
                    'no_devices': '📭 No devices found in the system.',
                    'room_not_found': '❌ Room \'{}\' not found in the system.',
                    'devices': 'Devices',
                    'buttons': 'Control Buttons',
                    'total': 'Total',
                    'device_unit': 'device' if target_room != 'all' else 'devices',
                    'button_unit': 'button' if target_room != 'all' else 'buttons'
                }
            }
            
            msg = messages[lang]
            
            if not device_list or not isinstance(device_list, dict):
                return msg['error_no_data']
            
            # Extract device data
            data = device_list.get('data', {})
            rooms = data.get('rooms', [])
            
            if not rooms:
                return msg['no_devices']
            
            # Filter rooms if specific room requested
            if target_room and target_room != 'all':
                logger.info(f"🔍 Filtering for room: '{target_room}'")
                logger.info(f"🔍 Available rooms: {[r.get('room_name') for r in rooms]}")
                
                # Use flexible room name matching
                matched_rooms = []
                for room in rooms:
                    room_name = room.get('room_name', '')
                    if self._match_room_name(target_room, room_name):
                        matched_rooms.append(room)
                        logger.info(f"✅ Matched: '{target_room}' → '{room_name}'")
                
                rooms = matched_rooms
                logger.info(f"🔍 Filtered rooms: {[r.get('room_name') for r in rooms]}")
                
                if not rooms:
                    return msg['room_not_found'].format(target_room)
            
            # Build response
            response_lines = []
            response_lines.append(msg['title'] + "\n")
            
            total_devices = 0
            total_buttons = 0
            
            for room in rooms:
                room_name = room.get('room_name', 'Unknown Room')
                devices = room.get('devices', [])
                buttons = room.get('buttons', [])
                
                if not devices and not buttons:
                    continue
                
                # Count items
                device_count = len(devices)
                button_count = len(buttons)
                total_devices += device_count
                total_buttons += button_count
                
                response_lines.append(f"\n📍 **{room_name}**")
                
                # Show devices
                if devices:
                    response_lines.append(f"  🔌 **{msg['devices']}** ({device_count}):")
                    for device in devices:
                        device_name = device.get('name', 'Unknown Device')
                        device_status = device.get('device_status', 'Unknown')
                        status_icon = '🟢' if 'kết nối' in device_status.lower() or 'connected' in device_status.lower() else '⚪'
                        response_lines.append(f"    • **{device_name}** - {status_icon} {device_status}")
                
                # Show buttons
                if buttons:
                    response_lines.append(f"  🎚️ **{msg['buttons']}** ({button_count}):")
                    for btn in buttons:
                        btn_name = btn.get('name', 'Unknown Button')
                        btn_status = btn.get('status', 'Unknown')
                        status_icon = '🟢' if btn_status.lower() in ['bật', 'on'] else '⚪'
                        response_lines.append(f"    • **{btn_name}** - {status_icon} {btn_status}")
            
            if total_devices == 0 and total_buttons == 0:
                return msg['no_devices']
            
            # Build summary with proper singular/plural handling
            if lang == 'en':
                device_word = 'device' if total_devices == 1 else 'devices'
                button_word = 'button' if total_buttons == 1 else 'buttons'
                response_lines.append(f"\n📊 **{msg['total']}**: {total_devices} {device_word}, {total_buttons} {button_word}")
            else:
                response_lines.append(f"\n📊 **{msg['total']}**: {total_devices} {msg['device_unit']}, {total_buttons} {msg['button_unit']}")
            
            return '\n'.join(response_lines)
            
        except Exception as e:
            logger.error(f"❌ Error formatting device status: {str(e)}")
            return f"❌ Lỗi khi hiển thị thông tin thiết bị: {str(e)}"
    
    def should_use_fast_path(self, confidence_threshold: float = 0.85) -> bool:
        """
        Determine if fast-path should be used based on confidence threshold.
        
        Args:
            confidence_threshold: Minimum confidence to use fast-path (default: 0.85)
            
        Returns:
            True if should use fast-path
        """
        return True  # Can be made configurable based on system state


# Global instance for reuse
_fast_path_instance = None


def get_fast_path_classifier(verbose: bool = False) -> FastPathClassifier:
    """Get or create singleton FastPathClassifier instance"""
    global _fast_path_instance
    if _fast_path_instance is None:
        _fast_path_instance = FastPathClassifier(verbose=verbose)
    return _fast_path_instance
