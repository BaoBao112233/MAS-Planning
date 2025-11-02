"""
MCP Connection Pooling
Tái sử dụng MCP clients thay vì tạo mới mỗi lần
"""
import asyncio
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class MCPConnection:
    """Single MCP connection"""
    client: object  # MCPClient instance
    session: object  # Session instance
    created_at: datetime
    last_used: datetime
    use_count: int = 0
    is_healthy: bool = True


class MCPConnectionPool:
    """
    Connection pool for MCP clients
    Saves ~0.5-1s per tool call by reusing connections
    """
    
    def __init__(
        self,
        max_connections: int = 5,
        max_idle_time: int = 300,  # 5 minutes
        max_connection_age: int = 1800,  # 30 minutes
    ):
        self.max_connections = max_connections
        self.max_idle_time = max_idle_time
        self.max_connection_age = max_connection_age
        
        # Connection pools per server
        self.pools: Dict[str, list[MCPConnection]] = {}
        self.lock = asyncio.Lock()
        
        # Statistics
        self.stats = {
            'connections_created': 0,
            'connections_reused': 0,
            'connections_closed': 0,
            'cache_hits': 0,
            'cache_misses': 0,
        }
    
    async def get_connection(self, server_name: str) -> tuple:
        """
        Get or create MCP connection
        
        Returns:
            (client, session) tuple
        """
        async with self.lock:
            # Initialize pool for this server
            if server_name not in self.pools:
                self.pools[server_name] = []
            
            pool = self.pools[server_name]
            
            # Try to find healthy, non-expired connection
            for conn in pool:
                if await self._is_connection_valid(conn):
                    # Reuse existing connection
                    conn.last_used = datetime.now()
                    conn.use_count += 1
                    self.stats['connections_reused'] += 1
                    self.stats['cache_hits'] += 1
                    
                    logger.info(
                        f"♻️  Reusing MCP connection for {server_name} "
                        f"(uses: {conn.use_count})"
                    )
                    return conn.client, conn.session
            
            # No valid connection, create new one
            self.stats['cache_misses'] += 1
            return await self._create_connection(server_name)
    
    async def _create_connection(self, server_name: str) -> tuple:
        """Create new MCP connection"""
        from mcp import ClientSession
        from mcp.client.sse import sse_client
        
        logger.info(f"🔌 Creating new MCP connection for {server_name}")
        
        # Create new client
        async with sse_client(f"http://localhost:8000/sse/{server_name}") as streams:
            client, session = streams
            
            # Store in pool
            conn = MCPConnection(
                client=client,
                session=session,
                created_at=datetime.now(),
                last_used=datetime.now(),
            )
            
            pool = self.pools[server_name]
            pool.append(conn)
            
            # Cleanup old connections if pool is full
            if len(pool) > self.max_connections:
                await self._cleanup_old_connections(server_name)
            
            self.stats['connections_created'] += 1
            
            return client, session
    
    async def _is_connection_valid(self, conn: MCPConnection) -> bool:
        """Check if connection is valid"""
        now = datetime.now()
        
        # Check health flag
        if not conn.is_healthy:
            return False
        
        # Check age
        age = (now - conn.created_at).total_seconds()
        if age > self.max_connection_age:
            logger.debug(f"Connection expired (age: {age}s)")
            return False
        
        # Check idle time
        idle_time = (now - conn.last_used).total_seconds()
        if idle_time > self.max_idle_time:
            logger.debug(f"Connection idle too long ({idle_time}s)")
            return False
        
        # TODO: Add actual health check (ping MCP server)
        # For now, assume healthy
        
        return True
    
    async def _cleanup_old_connections(self, server_name: str):
        """Remove old/invalid connections"""
        pool = self.pools[server_name]
        valid_connections = []
        
        for conn in pool:
            if await self._is_connection_valid(conn):
                valid_connections.append(conn)
            else:
                await self._close_connection(conn)
        
        self.pools[server_name] = valid_connections
    
    async def _close_connection(self, conn: MCPConnection):
        """Close a connection"""
        try:
            # Mark as unhealthy
            conn.is_healthy = False
            
            # Close session if possible
            if hasattr(conn.session, 'close'):
                await conn.session.close()
            
            self.stats['connections_closed'] += 1
            logger.debug("🔌 Closed MCP connection")
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
    
    async def close_all(self):
        """Close all connections in all pools"""
        async with self.lock:
            for server_name, pool in self.pools.items():
                for conn in pool:
                    await self._close_connection(conn)
            
            self.pools.clear()
            logger.info("🔌 Closed all MCP connections")
    
    def get_stats(self) -> dict:
        """Get pool statistics"""
        pool_sizes = {
            server: len(pool) 
            for server, pool in self.pools.items()
        }
        
        hit_rate = (
            self.stats['cache_hits'] / 
            (self.stats['cache_hits'] + self.stats['cache_misses'])
            if (self.stats['cache_hits'] + self.stats['cache_misses']) > 0
            else 0
        )
        
        return {
            **self.stats,
            'pool_sizes': pool_sizes,
            'hit_rate': f"{hit_rate:.2%}",
        }


# ============================================================
# Global Pool Instance
# ============================================================

# Singleton pool instance
_pool: Optional[MCPConnectionPool] = None


def get_pool() -> MCPConnectionPool:
    """Get global connection pool"""
    global _pool
    if _pool is None:
        _pool = MCPConnectionPool(
            max_connections=5,
            max_idle_time=300,  # 5 minutes
            max_connection_age=1800,  # 30 minutes
        )
    return _pool


# ============================================================
# Integration Example
# ============================================================

async def enhanced_execute_tools_parallel(self, tools_to_execute: list) -> list:
    """
    Enhanced execute_tools_parallel with connection pooling
    
    Replace in ToolAgent.execute_tools_parallel():
    """
    from template.agent.api_client import get_api_client
    
    # Get connection pool
    pool = get_pool()
    
    async def execute_single_tool(tool):
        try:
            api_client = get_api_client()
            server_name = tool["server_name"]
            tool_name = tool["name"]
            arguments = tool["arguments"]
            
            # Use connection pool instead of creating new client
            client, session = await pool.get_connection(server_name)
            
            # Execute tool
            result = await api_client.execute_mcp_tool(
                client=client,
                session=session,
                tool_name=tool_name,
                arguments=arguments,
            )
            
            return {
                "tool": tool_name,
                "server": server_name,
                "arguments": arguments,
                "result": result,
                "status": "success",
            }
            
        except Exception as e:
            logger.error(f"Error executing {tool.get('name', 'unknown')}: {e}")
            return {
                "tool": tool.get("name", "unknown"),
                "server": tool.get("server_name", "unknown"),
                "arguments": tool.get("arguments", {}),
                "error": str(e),
                "status": "error",
            }
    
    # Execute tools in parallel
    tasks = [execute_single_tool(tool) for tool in tools_to_execute]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


# Original implementation for comparison
async def original_execute_tools_parallel(self, tools_to_execute: list) -> list:
    """
    Original implementation (creates new client each time)
    """
    from mcp.client.sse import sse_client
    from template.agent.api_client import get_api_client
    
    async def execute_single_tool(tool):
        try:
            api_client = get_api_client()
            server_name = tool["server_name"]
            tool_name = tool["name"]
            arguments = tool["arguments"]
            
            # ❌ Creates new client EVERY TIME (slow!)
            async with sse_client(
                f"http://localhost:8000/sse/{server_name}"
            ) as streams:
                client, session = streams
                
                result = await api_client.execute_mcp_tool(
                    client=client,
                    session=session,
                    tool_name=tool_name,
                    arguments=arguments,
                )
            
            return {
                "tool": tool_name,
                "server": server_name,
                "arguments": arguments,
                "result": result,
                "status": "success",
            }
            
        except Exception as e:
            logger.error(f"Error executing {tool.get('name', 'unknown')}: {e}")
            return {
                "tool": tool.get("name", "unknown"),
                "server": tool.get("server_name", "unknown"),
                "arguments": tool.get("arguments", {}),
                "error": str(e),
                "status": "error",
            }
    
    tasks = [execute_single_tool(tool) for tool in tools_to_execute]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


# ============================================================
# Cleanup on Shutdown
# ============================================================

async def cleanup_pool():
    """Call this on application shutdown"""
    pool = get_pool()
    await pool.close_all()
    
    # Print statistics
    stats = pool.get_stats()
    logger.info(f"📊 MCP Connection Pool Statistics:")
    logger.info(f"   Created: {stats['connections_created']}")
    logger.info(f"   Reused: {stats['connections_reused']}")
    logger.info(f"   Closed: {stats['connections_closed']}")
    logger.info(f"   Hit Rate: {stats['hit_rate']}")


# ============================================================
# Testing
# ============================================================

async def test_pool():
    """Test connection pooling"""
    pool = get_pool()
    
    # Simulate multiple tool calls to same server
    print("🧪 Testing connection pooling...")
    
    servers = ["device", "device", "weather", "device"]
    
    for i, server in enumerate(servers, 1):
        print(f"\n{i}. Getting connection for '{server}'")
        client, session = await pool.get_connection(server)
        print(f"   ✅ Got connection (type: {type(client).__name__})")
    
    # Print statistics
    stats = pool.get_stats()
    print(f"\n📊 Pool Statistics:")
    print(f"   Connections created: {stats['connections_created']}")
    print(f"   Connections reused: {stats['connections_reused']}")
    print(f"   Hit rate: {stats['hit_rate']}")
    print(f"   Pool sizes: {stats['pool_sizes']}")
    
    # Cleanup
    await pool.close_all()


if __name__ == "__main__":
    asyncio.run(test_pool())
