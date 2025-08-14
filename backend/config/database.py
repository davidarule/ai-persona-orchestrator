"""
Database configuration module for AI Persona Orchestrator
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class PostgreSQLConfig:
    """PostgreSQL database configuration"""
    host: str
    port: int
    database: str
    user: str
    password: str
    
    # Connection pool settings
    pool_min_size: int = 10
    pool_max_size: int = 20
    pool_max_queries: int = 50000
    pool_max_inactive_connection_lifetime: float = 300.0
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    
    # Query settings
    command_timeout: float = 60.0
    statement_cache_size: int = 1024
    
    @classmethod
    def from_env(cls) -> 'PostgreSQLConfig':
        """Create configuration from environment variables"""
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5434")),
            database=os.getenv("POSTGRES_DB", "ai_orchestrator"),
            user=os.getenv("POSTGRES_USER", "orchestrator_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            
            # Pool settings
            pool_min_size=int(os.getenv("DB_POOL_MIN_SIZE", "10")),
            pool_max_size=int(os.getenv("DB_POOL_MAX_SIZE", "20")),
            pool_max_queries=int(os.getenv("DB_POOL_MAX_QUERIES", "50000")),
            pool_max_inactive_connection_lifetime=float(
                os.getenv("DB_POOL_MAX_INACTIVE_LIFETIME", "300.0")
            ),
            
            # Retry settings
            max_retries=int(os.getenv("DB_MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("DB_RETRY_DELAY", "1.0")),
            retry_backoff=float(os.getenv("DB_RETRY_BACKOFF", "2.0")),
            
            # Query settings
            command_timeout=float(os.getenv("DB_COMMAND_TIMEOUT", "60.0")),
            statement_cache_size=int(os.getenv("DB_STATEMENT_CACHE_SIZE", "1024"))
        )
    
    def get_connection_string(self) -> str:
        """Get PostgreSQL connection string"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    def get_pool_config(self) -> Dict[str, Any]:
        """Get asyncpg pool configuration"""
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
            "min_size": self.pool_min_size,
            "max_size": self.pool_max_size,
            "max_queries": self.pool_max_queries,
            "max_inactive_connection_lifetime": self.pool_max_inactive_connection_lifetime,
            "command_timeout": self.command_timeout,
            "statement_cache_size": self.statement_cache_size
        }


@dataclass
class RedisConfig:
    """Redis configuration"""
    url: str
    decode_responses: bool = True
    max_connections: int = 50
    socket_keepalive: bool = True
    socket_keepalive_options: Optional[Dict[str, int]] = None
    health_check_interval: int = 30
    
    @classmethod
    def from_env(cls) -> 'RedisConfig':
        """Create configuration from environment variables"""
        return cls(
            url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=os.getenv("REDIS_DECODE_RESPONSES", "true").lower() == "true",
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
            socket_keepalive=os.getenv("REDIS_SOCKET_KEEPALIVE", "true").lower() == "true",
            health_check_interval=int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))
        )


@dataclass
class Neo4jConfig:
    """Neo4j configuration"""
    uri: str
    auth: tuple[str, str]
    max_connection_lifetime: int = 3600
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: float = 60.0
    
    @classmethod
    def from_env(cls) -> 'Neo4jConfig':
        """Create configuration from environment variables"""
        auth_str = os.getenv("NEO4J_AUTH", "neo4j/password")
        username, password = auth_str.split("/", 1)
        
        return cls(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(username, password),
            max_connection_lifetime=int(os.getenv("NEO4J_MAX_CONNECTION_LIFETIME", "3600")),
            max_connection_pool_size=int(os.getenv("NEO4J_MAX_POOL_SIZE", "50")),
            connection_acquisition_timeout=float(
                os.getenv("NEO4J_CONNECTION_TIMEOUT", "60.0")
            )
        )


class DatabaseConfig:
    """Main database configuration class"""
    
    def __init__(self):
        self.postgresql = PostgreSQLConfig.from_env()
        self.redis = RedisConfig.from_env()
        self.neo4j = Neo4jConfig.from_env()
    
    @property
    def is_configured(self) -> bool:
        """Check if all database configurations are valid"""
        return all([
            self.postgresql.password,
            self.postgresql.host,
            self.redis.url,
            self.neo4j.uri
        ])
    
    def get_health_check_config(self) -> Dict[str, Any]:
        """Get configuration for health checks"""
        return {
            "postgresql": {
                "host": self.postgresql.host,
                "port": self.postgresql.port,
                "database": self.postgresql.database
            },
            "redis": {
                "url": self.redis.url
            },
            "neo4j": {
                "uri": self.neo4j.uri
            }
        }


# Global configuration instance
db_config = DatabaseConfig()