"""
Unit tests for database configuration
"""

import pytest
import os
from backend.config.database import PostgreSQLConfig, RedisConfig, Neo4jConfig, DatabaseConfig


class TestPostgreSQLConfig:
    """Test PostgreSQL configuration"""
    
    def test_from_env_defaults(self):
        """Test creating config from environment with defaults"""
        config = PostgreSQLConfig.from_env()
        
        assert config.host == "localhost"
        assert config.port == 5434
        assert config.database == "ai_orchestrator"
        assert config.user == "orchestrator_user"
        assert config.pool_min_size == 10
        assert config.pool_max_size == 20
    
    def test_from_env_custom_values(self, monkeypatch):
        """Test creating config with custom environment values"""
        monkeypatch.setenv("POSTGRES_HOST", "custom-host")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        monkeypatch.setenv("DB_POOL_MIN_SIZE", "5")
        monkeypatch.setenv("DB_POOL_MAX_SIZE", "30")
        
        config = PostgreSQLConfig.from_env()
        
        assert config.host == "custom-host"
        assert config.port == 5433
        assert config.pool_min_size == 5
        assert config.pool_max_size == 30
    
    def test_get_connection_string(self):
        """Test connection string generation"""
        config = PostgreSQLConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
            password="test_pass"
        )
        
        expected = "postgresql://test_user:test_pass@localhost:5432/test_db"
        assert config.get_connection_string() == expected
    
    def test_get_pool_config(self):
        """Test pool configuration dictionary"""
        config = PostgreSQLConfig(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
            password="test_pass",
            pool_min_size=5,
            pool_max_size=15
        )
        
        pool_config = config.get_pool_config()
        
        assert pool_config["host"] == "localhost"
        assert pool_config["port"] == 5432
        assert pool_config["min_size"] == 5
        assert pool_config["max_size"] == 15
        assert "command_timeout" in pool_config


class TestRedisConfig:
    """Test Redis configuration"""
    
    def test_from_env_defaults(self):
        """Test creating config from environment with defaults"""
        config = RedisConfig.from_env()
        
        assert config.decode_responses is True
        assert config.max_connections == 50
        assert config.socket_keepalive is True
        assert config.health_check_interval == 30
    
    def test_from_env_custom_values(self, monkeypatch):
        """Test creating config with custom environment values"""
        monkeypatch.setenv("REDIS_URL", "redis://custom:6380")
        monkeypatch.setenv("REDIS_DECODE_RESPONSES", "false")
        monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "100")
        
        config = RedisConfig.from_env()
        
        assert config.url == "redis://custom:6380"
        assert config.decode_responses is False
        assert config.max_connections == 100


class TestNeo4jConfig:
    """Test Neo4j configuration"""
    
    def test_from_env_defaults(self):
        """Test creating config from environment with defaults"""
        config = Neo4jConfig.from_env()
        
        assert config.uri == "bolt://localhost:7687"
        assert config.auth[0] == "neo4j"
        assert config.max_connection_lifetime == 3600
        assert config.max_connection_pool_size == 50
    
    def test_from_env_custom_auth(self, monkeypatch):
        """Test parsing Neo4j auth from environment"""
        monkeypatch.setenv("NEO4J_AUTH", "custom_user/custom_pass")
        monkeypatch.setenv("NEO4J_URI", "bolt://neo4j-server:7688")
        
        config = Neo4jConfig.from_env()
        
        assert config.uri == "bolt://neo4j-server:7688"
        assert config.auth == ("custom_user", "custom_pass")


class TestDatabaseConfig:
    """Test main database configuration"""
    
    def test_initialization(self):
        """Test that all sub-configs are initialized"""
        config = DatabaseConfig()
        
        assert isinstance(config.postgresql, PostgreSQLConfig)
        assert isinstance(config.redis, RedisConfig)
        assert isinstance(config.neo4j, Neo4jConfig)
    
    def test_is_configured(self):
        """Test configuration validation"""
        config = DatabaseConfig()
        
        # Should be configured if passwords and hosts are set
        assert config.is_configured is True
    
    def test_health_check_config(self):
        """Test health check configuration generation"""
        config = DatabaseConfig()
        health_config = config.get_health_check_config()
        
        assert "postgresql" in health_config
        assert "redis" in health_config
        assert "neo4j" in health_config
        
        assert health_config["postgresql"]["port"] == 5434
        assert "url" in health_config["redis"]
        assert "uri" in health_config["neo4j"]