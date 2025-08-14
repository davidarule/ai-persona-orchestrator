"""
Database service layer for AI Persona Orchestrator
Provides connection management, query execution, and monitoring
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager
import asyncpg
import redis.asyncio as redis
from neo4j import AsyncGraphDatabase
import logging
from ..config.database import db_config

logger = logging.getLogger(__name__)


class DatabaseConnectionError(Exception):
    """Raised when database connection fails"""
    pass


class DatabaseManager:
    """Manages all database connections with pooling and monitoring"""
    
    def __init__(self):
        self.pg_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.neo4j_driver: Optional[Any] = None
        self._is_initialized = False
        
        # Connection metrics
        self.metrics = {
            "pg_queries": 0,
            "pg_errors": 0,
            "redis_commands": 0,
            "redis_errors": 0,
            "neo4j_queries": 0,
            "neo4j_errors": 0,
            "slow_queries": []
        }
    
    async def initialize(self):
        """Initialize all database connections with retry logic"""
        if self._is_initialized:
            return
        
        # Initialize PostgreSQL
        await self._init_postgresql()
        
        # Initialize Redis
        await self._init_redis()
        
        # Initialize Neo4j
        await self._init_neo4j()
        
        self._is_initialized = True
        logger.info("All database connections initialized successfully")
    
    async def _init_postgresql(self):
        """Initialize PostgreSQL connection pool with retry"""
        config = db_config.postgresql
        retry_count = 0
        
        while retry_count < config.max_retries:
            try:
                self.pg_pool = await asyncpg.create_pool(
                    **config.get_pool_config()
                )
                
                # Test connection
                async with self.pg_pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                
                logger.info(f"PostgreSQL connected: {config.host}:{config.port}/{config.database}")
                return
                
            except Exception as e:
                retry_count += 1
                if retry_count >= config.max_retries:
                    raise DatabaseConnectionError(f"Failed to connect to PostgreSQL: {e}")
                
                wait_time = config.retry_delay * (config.retry_backoff ** (retry_count - 1))
                logger.warning(f"PostgreSQL connection failed, retry {retry_count}/{config.max_retries} in {wait_time}s")
                await asyncio.sleep(wait_time)
    
    async def _init_redis(self):
        """Initialize Redis connection with retry"""
        config = db_config.redis
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                self.redis_client = await redis.from_url(
                    config.url,
                    decode_responses=config.decode_responses,
                    max_connections=config.max_connections,
                    socket_keepalive=config.socket_keepalive,
                    health_check_interval=config.health_check_interval
                )
                
                # Test connection
                await self.redis_client.ping()
                
                logger.info(f"Redis connected: {config.url}")
                return
                
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise DatabaseConnectionError(f"Failed to connect to Redis: {e}")
                
                wait_time = 2 ** retry_count
                logger.warning(f"Redis connection failed, retry {retry_count}/{max_retries} in {wait_time}s")
                await asyncio.sleep(wait_time)
    
    async def _init_neo4j(self):
        """Initialize Neo4j connection"""
        config = db_config.neo4j
        
        try:
            self.neo4j_driver = AsyncGraphDatabase.driver(
                config.uri,
                auth=config.auth,
                max_connection_lifetime=config.max_connection_lifetime,
                max_connection_pool_size=config.max_connection_pool_size,
                connection_acquisition_timeout=config.connection_acquisition_timeout
            )
            
            # Test connection
            async with self.neo4j_driver.session() as session:
                await session.run("RETURN 1")
            
            logger.info(f"Neo4j connected: {config.uri}")
            
        except Exception as e:
            # Neo4j is optional, so we just log the error
            logger.warning(f"Neo4j connection failed (optional): {e}")
            self.neo4j_driver = None
    
    async def close(self):
        """Close all database connections"""
        if self.pg_pool:
            await self.pg_pool.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        if self.neo4j_driver:
            await self.neo4j_driver.close()
        
        self._is_initialized = False
        logger.info("All database connections closed")
    
    @asynccontextmanager
    async def acquire_pg_connection(self):
        """Acquire a PostgreSQL connection from the pool"""
        if not self.pg_pool:
            raise DatabaseConnectionError("PostgreSQL pool not initialized")
        
        start_time = time.time()
        async with self.pg_pool.acquire() as conn:
            try:
                yield conn
            finally:
                # Track query time
                query_time = time.time() - start_time
                if query_time > 1.0:  # Log slow queries
                    self.metrics["slow_queries"].append({
                        "type": "postgresql",
                        "time": query_time,
                        "timestamp": time.time()
                    })
    
    async def execute_query(
        self, 
        query: str, 
        *args, 
        fetch_one: bool = False,
        timeout: Optional[float] = None
    ) -> Union[List[asyncpg.Record], asyncpg.Record, None]:
        """Execute a PostgreSQL query with monitoring"""
        try:
            async with self.acquire_pg_connection() as conn:
                if timeout:
                    result = await asyncio.wait_for(
                        conn.fetch(query, *args) if not fetch_one else conn.fetchrow(query, *args),
                        timeout=timeout
                    )
                else:
                    result = await conn.fetch(query, *args) if not fetch_one else await conn.fetchrow(query, *args)
                
                self.metrics["pg_queries"] += 1
                return result
                
        except Exception as e:
            self.metrics["pg_errors"] += 1
            logger.error(f"PostgreSQL query error: {e}")
            raise
    
    async def execute_many(self, query: str, args_list: List[tuple]) -> None:
        """Execute multiple queries in a transaction"""
        try:
            async with self.acquire_pg_connection() as conn:
                async with conn.transaction():
                    await conn.executemany(query, args_list)
                
                self.metrics["pg_queries"] += len(args_list)
                
        except Exception as e:
            self.metrics["pg_errors"] += 1
            logger.error(f"PostgreSQL bulk insert error: {e}")
            raise
    
    async def redis_execute(self, command: str, *args, **kwargs) -> Any:
        """Execute a Redis command with monitoring"""
        if not self.redis_client:
            raise DatabaseConnectionError("Redis client not initialized")
        
        try:
            method = getattr(self.redis_client, command)
            result = await method(*args, **kwargs)
            self.metrics["redis_commands"] += 1
            return result
            
        except Exception as e:
            self.metrics["redis_errors"] += 1
            logger.error(f"Redis command error: {e}")
            raise
    
    async def neo4j_execute(self, query: str, parameters: Optional[Dict] = None) -> List[Dict]:
        """Execute a Neo4j query"""
        if not self.neo4j_driver:
            return []  # Neo4j is optional
        
        try:
            async with self.neo4j_driver.session() as session:
                result = await session.run(query, parameters or {})
                records = [record.data() async for record in result]
                self.metrics["neo4j_queries"] += 1
                return records
                
        except Exception as e:
            self.metrics["neo4j_errors"] += 1
            logger.error(f"Neo4j query error: {e}")
            raise
    
    def get_pool_status(self) -> Dict[str, Any]:
        """Get current connection pool status"""
        status = {
            "postgresql": {
                "initialized": bool(self.pg_pool),
                "min_size": self.pg_pool._minsize if self.pg_pool else 0,
                "max_size": self.pg_pool._maxsize if self.pg_pool else 0,
                "current_size": len(self.pg_pool._holders) if self.pg_pool else 0,
                "queries": self.metrics["pg_queries"],
                "errors": self.metrics["pg_errors"]
            },
            "redis": {
                "initialized": bool(self.redis_client),
                "commands": self.metrics["redis_commands"],
                "errors": self.metrics["redis_errors"]
            },
            "neo4j": {
                "initialized": bool(self.neo4j_driver),
                "queries": self.metrics["neo4j_queries"],
                "errors": self.metrics["neo4j_errors"]
            },
            "slow_queries": len(self.metrics["slow_queries"])
        }
        
        return status
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all database connections"""
        health = {
            "postgresql": False,
            "redis": False,
            "neo4j": False
        }
        
        # Check PostgreSQL
        try:
            if self.pg_pool:
                await self.execute_query("SELECT 1", fetch_one=True)
                health["postgresql"] = True
        except:
            pass
        
        # Check Redis
        try:
            if self.redis_client:
                await self.redis_client.ping()
                health["redis"] = True
        except:
            pass
        
        # Check Neo4j
        try:
            if self.neo4j_driver:
                await self.neo4j_execute("RETURN 1")
                health["neo4j"] = True
        except:
            pass
        
        return health


# Global database manager instance
db_manager = DatabaseManager()