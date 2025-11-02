"""
Device List Caching Optimization
Giảm Tool Agent iterations từ 3 → 2 (bỏ qua get_device_list)
"""
import asyncio
import time
import json
import hashlib
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import logging
from template.message.message import HumanMessage

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry với TTL"""
    data: Any
    timestamp: float
    ttl: float = 300.0  # 5 minutes default
    
    def is_valid(self) -> bool:
        """Check if cache entry is still valid"""
        return (time.time() - self.timestamp) < self.ttl
    
    def age(self) -> float:
        """Get age in seconds"""
        return time.time() - self.timestamp


class DeviceCache:
    """
    Smart cache for device list and device information
    Giảm iterations bằng cách cache device list response
    """
    
    def __init__(self, default_ttl: float = 300.0, verbose: bool = False):
        self.default_ttl = default_ttl
        self.verbose = verbose
        self._cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached data if valid"""
        entry = self._cache.get(key)
        
        if entry is None:
            self._misses += 1
            if self.verbose:
                logger.info(f"❌ Cache miss: {key}")
            return None
        
        if not entry.is_valid():
            # Expired
            del self._cache[key]
            self._misses += 1
            if self.verbose:
                logger.info(f"⏰ Cache expired: {key} (age: {entry.age():.1f}s)")
            return None
        
        # Valid cache hit
        self._hits += 1
        if self.verbose:
            logger.info(f"✅ Cache hit: {key} (age: {entry.age():.1f}s)")
        
        return entry.data
    
    def set(self, key: str, data: Any, ttl: Optional[float] = None):
        """Set cache entry"""
        ttl = ttl or self.default_ttl
        self._cache[key] = CacheEntry(
            data=data,
            timestamp=time.time(),
            ttl=ttl
        )
        
        if self.verbose:
            logger.info(f"💾 Cached: {key} (TTL: {ttl}s)")
    
    def invalidate(self, key: str):
        """Manually invalidate cache entry"""
        if key in self._cache:
            del self._cache[key]
            if self.verbose:
                logger.info(f"🗑️ Invalidated: {key}")
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()
        if self.verbose:
            logger.info(f"🧹 Cache cleared")
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        return {
            'hits': self._hits,
            'misses': self._misses,
            'total_requests': total,
            'hit_rate': hit_rate,
            'entries': len(self._cache),
            'valid_entries': sum(1 for e in self._cache.values() if e.is_valid())
        }


class SmartDeviceCache:
    """
    Enhanced device cache với user và token awareness
    """
    
    def __init__(self, default_ttl: float = 300.0, verbose: bool = False):
        self.cache = DeviceCache(default_ttl, verbose)
        self.verbose = verbose
    
    def _make_key(self, token: str, key_type: str = 'devices') -> str:
        """Generate cache key from token"""
        # Use hash of token for privacy
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        return f"{key_type}:{token_hash}"
    
    def get_device_list(self, token: str) -> Optional[Dict]:
        """Get cached device list for user"""
        key = self._make_key(token, 'devices')
        return self.cache.get(key)
    
    def set_device_list(self, token: str, devices: Dict, ttl: Optional[float] = None):
        """Cache device list for user"""
        key = self._make_key(token, 'devices')
        self.cache.set(key, devices, ttl)
    
    def invalidate_user_cache(self, token: str):
        """Invalidate all cache for a user"""
        key = self._make_key(token, 'devices')
        self.cache.invalidate(key)
    
    def should_refresh(self, token: str, refresh_threshold: float = 240.0) -> bool:
        """
        Check if cache should be refreshed proactively
        
        Args:
            refresh_threshold: Refresh if age > this value (default 4 minutes)
        """
        key = self._make_key(token, 'devices')
        entry = self.cache._cache.get(key)
        
        if entry is None:
            return True
        
        return entry.age() > refresh_threshold


# ============================================================
# Integration with ToolAgent
# ============================================================

class CachedToolAgent:
    """
    Enhanced Tool Agent với device caching
    
    Add to ToolAgent.__init__:
        self.device_cache = SmartDeviceCache(verbose=self.verbose)
    """
    
    async def reason_and_plan_cached(self, state):
        """Enhanced reasoning với device cache injection"""
        
        # Check if we have cached device list
        token = state.get('token', '')
        cached_devices = self.device_cache.get_device_list(token)
        
        if cached_devices:
            # Inject cached device list into context
            device_info = json.dumps(cached_devices, indent=2, ensure_ascii=False)
            
            cache_msg = f"""
[CACHED DEVICE LIST - Use this instead of calling get_device_list]

{device_info}

Instructions:
- This device list is fresh (cached {self.device_cache.cache._cache.get(self.device_cache._make_key(token, 'devices')).age():.1f}s ago)
- Use button IDs directly for device control
- DO NOT call get_device_list again
- Proceed directly to control tools
"""
            
            # Insert cache message before reasoning
            if 'messages' in state and len(state['messages']) > 0:
                # Insert after system message
                state['messages'].insert(1, HumanMessage(content=cache_msg))
            
            if self.verbose:
                logger.info("📋 Injected cached device list into context")
        
        # Continue with normal reasoning
        return await self.original_reason_and_plan(state)
    
    async def execute_tools_cached(self, state):
        """Enhanced execution với cache update"""
        
        # Execute tools normally
        result = await self.original_execute_tools(state)
        
        # Update cache if get_device_list was called
        tool_results = result.get('tool_results', [])
        token = state.get('token', '')
        
        for tool_result in tool_results:
            if tool_result.get('tool_name') == 'get_device_list':
                if tool_result.get('success'):
                    devices = tool_result.get('content')
                    self.device_cache.set_device_list(token, devices)
                    
                    if self.verbose:
                        logger.info("💾 Updated device list cache")
        
        return result


# ============================================================
# Testing
# ============================================================

async def test_device_cache():
    """Test device cache functionality"""
    print("=" * 60)
    print("Device Cache Test")
    print("=" * 60)
    
    cache = SmartDeviceCache(default_ttl=10, verbose=True)
    
    # Simulate token
    token = "test_token_12345"
    
    # Simulate device list
    devices = {
        "devices": [
            {"id": 1662, "name": "Đèn 1", "room": "bedroom"},
            {"id": 1663, "name": "Đèn 2", "room": "living room"},
        ]
    }
    
    # Test 1: Set cache
    print("\n1. Setting cache...")
    cache.set_device_list(token, devices)
    
    # Test 2: Get cache (should hit)
    print("\n2. Getting cache (should hit)...")
    result = cache.get_device_list(token)
    print(f"   Result: {result}")
    
    # Test 3: Get again (should hit)
    print("\n3. Getting cache again (should hit)...")
    result = cache.get_device_list(token)
    print(f"   Result: {result}")
    
    # Test 4: Wait for expiration
    print("\n4. Waiting 11 seconds for expiration...")
    await asyncio.sleep(11)
    
    # Test 5: Get expired cache (should miss)
    print("\n5. Getting cache after expiration (should miss)...")
    result = cache.get_device_list(token)
    print(f"   Result: {result}")
    
    # Test 6: Stats
    print("\n6. Cache statistics:")
    stats = cache.cache.stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_device_cache())
