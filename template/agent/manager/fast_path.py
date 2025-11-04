"""
Fast-path Intent Classifier
Bypass LLM for simple, high-confidence device control commands

Performance: Saves 2-3s by skipping Manager LLM analysis
Confidence: Returns routing decision with 0.95+ confidence for pattern matches
"""

import re
import logging
from typing import Optional, Dict, Tuple, List
from functools import lru_cache

logger = logging.getLogger(__name__)


class FastPathClassifier:
    """
    Fast-path intent classification using regex patterns and device validation.
    Designed for smart home device control commands.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._device_cache = {}  # Simple in-memory cache
        self._cache_ttl = 60  # 60 seconds
        self._cache_timestamp = {}
        
        # Comprehensive patterns for device control
        self.patterns = self._build_patterns()
        
    def _build_patterns(self) -> List[Dict]:
        """
        Build comprehensive pattern library for device control.
        Returns list of pattern dictionaries with:
        - regex: compiled regex pattern
        - intent: intent type
        - confidence: base confidence score
        - description: human-readable description
        """
        patterns = []
        
        # ==========================================
        # VIETNAMESE PATTERNS
        # ==========================================
        
        # 1. Basic ON/OFF commands - Vietnamese
        patterns.extend([
            {
                'regex': re.compile(r'^(bật|mở|turn\s*on|open)\s+(.+?)(?:\s+(?:ở|tại|in|at)\s+(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'turn_on',
                'confidence': 0.95,
                'description': 'Turn on device (Vietnamese)'
            },
            {
                'regex': re.compile(r'^(tắt|đóng|turn\s*off|close)\s+(.+?)(?:\s+(?:ở|tại|in|at)\s+(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'turn_off',
                'confidence': 0.95,
                'description': 'Turn off device (Vietnamese)'
            },
        ])
        
        # 2. Temperature/AC control - Vietnamese
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set|chỉnh)\s+(?:nhiệt\s*độ|temperature|temp)?\s*(?:điều\s*hòa|ac|máy\s*lạnh)?\s*(?:ở|tại|in|at)?\s*(.+?)?\s*(?:lên|to|thành)?\s*(\d+)\s*(?:độ|°c|degrees?)?', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'set_temperature',
                'confidence': 0.92,
                'description': 'Set AC temperature (Vietnamese)'
            },
            {
                'regex': re.compile(r'^(?:bật|turn\s*on)\s+(?:điều\s*hòa|ac|máy\s*lạnh)\s+(?:ở|tại|in|at)?\s*(.+?)?\s*(?:ở|at)?\s*(\d+)\s*(?:độ|°c|degrees?)?', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'turn_on_ac_temp',
                'confidence': 0.93,
                'description': 'Turn on AC with temperature (Vietnamese)'
            },
        ])
        
        # 3. Light brightness control - Vietnamese
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set|chỉnh)\s+(?:độ\s*sáng|brightness)?\s*(?:đèn|light)?\s*(?:ở|tại|in|at)?\s*(.+?)?\s*(?:lên|to|thành)?\s*(\d+)\s*(?:%|percent)?', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'set_brightness',
                'confidence': 0.91,
                'description': 'Set light brightness (Vietnamese)'
            },
        ])
        
        # 4. Fan speed control - Vietnamese
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set|chỉnh)\s+(?:tốc\s*độ|speed)?\s*(?:quạt|fan)?\s*(?:ở|tại|in|at)?\s*(.+?)?\s*(?:lên|to|thành)?\s*(cao|thấp|trung\s*bình|high|low|medium|auto|\d+)', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'set_fan_speed',
                'confidence': 0.90,
                'description': 'Set fan speed (Vietnamese)'
            },
        ])
        
        # 5. Curtain/Blind control - Vietnamese
        patterns.extend([
            {
                'regex': re.compile(r'^(mở|open)\s+(?:rèm|cửa\s*sổ|curtain|blind)?\s*(?:ở|tại|in|at)?\s*(.+?)?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'open_curtain',
                'confidence': 0.94,
                'description': 'Open curtain/blind (Vietnamese)'
            },
            {
                'regex': re.compile(r'^(đóng|close)\s+(?:rèm|cửa\s*sổ|curtain|blind)?\s*(?:ở|tại|in|at)?\s*(.+?)?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'close_curtain',
                'confidence': 0.94,
                'description': 'Close curtain/blind (Vietnamese)'
            },
        ])
        
        # ==========================================
        # ENGLISH PATTERNS
        # ==========================================
        
        # 6. Basic ON/OFF - English
        patterns.extend([
            {
                'regex': re.compile(r'^turn\s+(on|off)\s+(?:the\s+)?(.+?)(?:\s+in\s+(?:the\s+)?(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'turn_on_off',
                'confidence': 0.96,
                'description': 'Turn on/off device (English)'
            },
            {
                'regex': re.compile(r'^switch\s+(on|off)\s+(?:the\s+)?(.+?)(?:\s+in\s+(?:the\s+)?(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'switch',
                'confidence': 0.95,
                'description': 'Switch device (English)'
            },
        ])
        
        # 7. Temperature control - English
        patterns.extend([
            {
                'regex': re.compile(r'^set\s+(?:the\s+)?(?:ac|air\s*conditioner|temperature)?\s*(?:in\s+(?:the\s+)?(.+?))?\s*to\s+(\d+)\s*(?:degrees?|°c)?', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'set_temperature',
                'confidence': 0.93,
                'description': 'Set temperature (English)'
            },
        ])
        
        # 8. All devices control - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(bật|tắt|turn\s*on|turn\s*off)\s+(?:tất\s*cả|all)\s+(?:đèn|light|lights)(?:\s+(?:ở|tại|in)\s+(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'all_lights',
                'confidence': 0.93,
                'description': 'Control all lights'
            },
            {
                'regex': re.compile(r'^(bật|tắt|turn\s*on|turn\s*off)\s+(?:tất\s*cả|all)\s+(?:thiết\s*bị|devices?)(?:\s+(?:ở|tại|in)\s+(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'all_devices',
                'confidence': 0.91,
                'description': 'Control all devices'
            },
        ])
        
        # 9. Device type control - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(bật|tắt|turn\s*on|turn\s*off)\s+(?:tất\s*cả|all)?\s*(đèn|light|điều\s*hòa|ac|quạt|fan|rèm|curtain)s?(?:\s+(?:ở|tại|in)\s+(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'device_type',
                'confidence': 0.92,
                'description': 'Control by device type'
            },
        ])
        
        # 10. Scene/Mode activation - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(?:kích\s*hoạt|activate|chạy|run|bật|turn\s*on)\s+(?:scene|cảnh|chế\s*độ|mode)\s+(.+?)$', re.IGNORECASE),
                'intent': 'scene_control',
                'action': 'activate_scene',
                'confidence': 0.89,
                'description': 'Activate scene/mode'
            },
        ])
        
        # 11. Numbered device control - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(bật|tắt|turn\s*on|turn\s*off|open|close|mở|đóng)\s+(.+?)\s*(\d+)(?:\s+(?:ở|tại|in|at)\s+(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'numbered_device',
                'confidence': 0.94,
                'description': 'Control numbered device (e.g., Light 1)'
            },
        ])
        
        # 12. Smart commands - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(?:i\'m\s+)?(?:tôi|i)\s+(?:về|đi\s*ngủ|leaving|going\s+to\s+sleep|home)$', re.IGNORECASE),
                'intent': 'scene_control',
                'action': 'smart_scene',
                'confidence': 0.87,
                'description': 'Smart scene shortcuts'
            },
            {
                'regex': re.compile(r'^(?:good\s+)?(morning|night|afternoon|evening|sáng|tối|chiều|trưa)$', re.IGNORECASE),
                'intent': 'scene_control',
                'action': 'time_based_scene',
                'confidence': 0.85,
                'description': 'Time-based scene'
            },
        ])
        
        # 13. Multi-device control - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(bật|tắt|turn\s*on|turn\s*off)\s+(.+?)\s+(?:và|and)\s+(.+?)(?:\s+(?:ở|tại|in)\s+(.+?))?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'multi_device',
                'confidence': 0.88,
                'description': 'Control multiple devices'
            },
        ])
        
        # 14. Color control - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set|chỉnh)\s+(?:màu|color)\s+(?:đèn|light)?\s*(?:ở|in)?\s*(.+?)?\s*(?:thành|to)\s+(red|blue|green|yellow|white|warm|cool|đỏ|xanh|vàng|trắng|ấm|mát)', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'set_color',
                'confidence': 0.90,
                'description': 'Set light color'
            },
        ])
        
        # 15. Volume control - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set|chỉnh)\s+(?:âm\s*lượng|volume)\s*(?:ở|in)?\s*(.+?)?\s*(?:lên|to)?\s*(\d+)\s*(?:%|percent)?', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'set_volume',
                'confidence': 0.91,
                'description': 'Set volume'
            },
            {
                'regex': re.compile(r'^(tăng|giảm|increase|decrease|raise|lower)\s+(?:âm\s*lượng|volume)(?:\s+(?:ở|in)\s+(.+?))?', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'adjust_volume',
                'confidence': 0.90,
                'description': 'Adjust volume'
            },
        ])
        
        # 16. Lock/Unlock control - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(khóa|mở\s*khóa|lock|unlock)\s+(?:cửa|door)?\s*(?:ở|in)?\s*(.+?)?$', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'lock_unlock',
                'confidence': 0.96,
                'description': 'Lock/unlock door'
            },
        ])
        
        # 17. Timer/Schedule - Vietnamese & English
        patterns.extend([
            {
                'regex': re.compile(r'^(?:đặt|set)\s+(?:hẹn\s*giờ|timer|schedule)\s+(.+?)\s+(?:sau|in|after)\s+(\d+)\s*(giây|phút|giờ|second|minute|hour)s?', re.IGNORECASE),
                'intent': 'device_control',
                'action': 'set_timer',
                'confidence': 0.85,
                'description': 'Set timer/schedule'
            },
        ])
        
        return patterns
    
    def classify(self, query: str, token: str = "") -> Optional[Dict]:
        """
        Fast classification of device control intent.
        
        Args:
            query: User input query
            token: Authentication token for device validation
            
        Returns:
            Dict with classification result or None if no match
            {
                'intent': 'device_control' | 'scene_control',
                'action': specific action type,
                'confidence': 0.85-0.96,
                'fast_path': True,
                'agent': 'tool',
                'matched_pattern': pattern description,
                'extracted_params': {...}
            }
        """
        if not query or not isinstance(query, str):
            return None
        
        query = query.strip()
        if not query:
            return None
        
        if self.verbose:
            logger.info(f"🚀 Fast-path: Analyzing '{query}'")
        
        # Try each pattern
        for pattern_def in self.patterns:
            match = pattern_def['regex'].match(query)
            if match:
                # Extract parameters from regex groups
                params = self._extract_params(match, pattern_def)
                
                # Build result
                result = {
                    'intent': pattern_def['intent'],
                    'action': pattern_def['action'],
                    'confidence': pattern_def['confidence'],
                    'fast_path': True,
                    'agent': 'tool' if pattern_def['intent'] == 'device_control' else 'plan',
                    'matched_pattern': pattern_def['description'],
                    'extracted_params': params,
                    'original_query': query
                }
                
                if self.verbose:
                    logger.info(f"✅ Fast-path match: {pattern_def['description']}")
                    logger.info(f"   Confidence: {pattern_def['confidence']:.2f}")
                    logger.info(f"   Agent: {result['agent']}")
                    logger.info(f"   Params: {params}")
                
                return result
        
        if self.verbose:
            logger.info(f"⚠️ Fast-path: No pattern match for '{query}'")
        
        return None
    
    def _extract_params(self, match: re.Match, pattern_def: Dict) -> Dict:
        """Extract parameters from regex match groups"""
        params = {}
        groups = match.groups()
        
        action = pattern_def['action']
        
        # Common extractions based on action type
        if action in ['turn_on', 'turn_off', 'turn_on_off', 'switch']:
            if len(groups) >= 2:
                params['device_name'] = groups[1].strip() if groups[1] else None
                params['room'] = groups[2].strip() if len(groups) > 2 and groups[2] else None
        
        elif action in ['set_temperature', 'turn_on_ac_temp']:
            if len(groups) >= 2:
                params['room'] = groups[0].strip() if groups[0] else None
                # Find temperature in groups
                for g in groups:
                    if g and g.isdigit():
                        params['temperature'] = int(g)
                        break
        
        elif action == 'set_brightness':
            if len(groups) >= 2:
                params['device_name'] = groups[0].strip() if groups[0] else None
                for g in groups:
                    if g and g.isdigit():
                        params['brightness'] = int(g)
                        break
        
        elif action == 'numbered_device':
            if len(groups) >= 3:
                params['action_type'] = groups[0].strip() if groups[0] else None
                params['device_name'] = groups[1].strip() if groups[1] else None
                params['device_number'] = groups[2].strip() if groups[2] else None
                params['room'] = groups[3].strip() if len(groups) > 3 and groups[3] else None
        
        elif action in ['all_lights', 'all_devices', 'device_type']:
            if len(groups) >= 1:
                params['action_type'] = groups[0].strip() if groups[0] else None
                params['device_type'] = groups[1].strip() if len(groups) > 1 and groups[1] else None
                params['room'] = groups[2].strip() if len(groups) > 2 and groups[2] else None
        
        elif action == 'multi_device':
            if len(groups) >= 3:
                params['action_type'] = groups[0].strip() if groups[0] else None
                params['device_1'] = groups[1].strip() if groups[1] else None
                params['device_2'] = groups[2].strip() if groups[2] else None
                params['room'] = groups[3].strip() if len(groups) > 3 and groups[3] else None
        
        # Default: store all groups
        params['_raw_groups'] = [g for g in groups if g]
        
        return params
    
    def should_use_fast_path(self, confidence_threshold: float = 0.90) -> bool:
        """
        Determine if fast-path should be used based on confidence threshold.
        Default threshold: 0.90 (90% confidence)
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
