"""
Integration tests for database layer with real connections
"""

import pytest
import asyncio
from backend.services.database import DatabaseManager, DatabaseConnectionError
from backend.utils.db_utils import QueryBuilder


@pytest.mark.integration
class TestDatabaseManager:
    """Test database manager with real connections"""
    
    async def test_initialize_all_connections(self, db):
        """Test that all database connections initialize properly"""
        # db fixture already initializes connections
        assert db._is_initialized is True
        assert db.pg_pool is not None
        assert db.redis_client is not None
        # Neo4j might be None if not available
    
    async def test_postgresql_connection(self, db):
        """Test PostgreSQL connection and basic operations"""
        # Test simple query
        result = await db.execute_query(
            "SELECT version()",
            fetch_one=True
        )
        assert result is not None
        assert "PostgreSQL" in result["version"]
        
        # Test query with parameters
        result = await db.execute_query(
            "SELECT $1::text as test_value",
            "test_string",
            fetch_one=True
        )
        assert result["test_value"] == "test_string"
    
    async def test_postgresql_table_queries(self, db):
        """Test queries against actual tables"""
        # Count persona types
        result = await db.execute_query(
            "SELECT COUNT(*) as count FROM orchestrator.persona_types",
            fetch_one=True
        )
        assert result["count"] >= 25  # Should have at least 25 persona types
        
        # Count workflows
        result = await db.execute_query(
            "SELECT COUNT(*) as count FROM orchestrator.workflow_definitions",
            fetch_one=True
        )
        assert result["count"] >= 43  # At least 18 system + 25 persona workflows
    
    async def test_postgresql_transaction(self, db):
        """Test transaction handling"""
        try:
            async with db.acquire_pg_connection() as conn:
                async with conn.transaction():
                    # Insert test data
                    await conn.execute("""
                        INSERT INTO orchestrator.mcp_servers (server_name, server_type)
                        VALUES ($1, $2)
                    """, "TEST_SERVER", "test")
                    
                    # Verify insert within transaction
                    result = await conn.fetchrow(
                        "SELECT * FROM orchestrator.mcp_servers WHERE server_name = $1",
                        "TEST_SERVER"
                    )
                    assert result is not None
                    
                    # Rollback by raising exception
                    raise Exception("Test rollback")
        except Exception as e:
            # Expected - transaction should rollback
            assert str(e) == "Test rollback"
    
        # Verify rollback worked - data should not exist
        result = await db.execute_query(
            "SELECT * FROM orchestrator.mcp_servers WHERE server_name = $1",
            "TEST_SERVER",
            fetch_one=True
        )
        assert result is None
    
    async def test_concurrent_queries(self, db):
        """Test concurrent query execution"""
        # Run 10 queries concurrently
        tasks = []
        for i in range(10):
            task = db.execute_query(
                "SELECT pg_sleep(0.01), $1::int as num",
                i,
                fetch_one=True
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Verify all queries completed
        assert len(results) == 10
        for i, result in enumerate(results):
            assert result["num"] == i
    
    async def test_redis_operations(self, db):
        """Test Redis operations"""
        test_key = "test:integration:key"
        test_value = "test_value_123"
        
        # Set value
        await db.redis_execute("set", test_key, test_value)
        
        # Get value
        result = await db.redis_execute("get", test_key)
        assert result == test_value
        
        # Delete key
        await db.redis_execute("delete", test_key)
        
        # Verify deletion
        result = await db.redis_execute("get", test_key)
        assert result is None
    
    async def test_redis_pubsub(self, db):
        """Test Redis pub/sub functionality"""
        channel = "test:channel"
        message = "test_message"
        
        # Create pubsub
        pubsub = db.redis_client.pubsub()
        await pubsub.subscribe(channel)
        
        # Publish message
        await db.redis_execute("publish", channel, message)
        
        # Read message (with timeout)
        try:
            async with asyncio.timeout(2):
                async for msg in pubsub.listen():
                    if msg["type"] == "message":
                        assert msg["data"] == message
                        break
        except asyncio.TimeoutError:
            pytest.fail("Did not receive pubsub message")
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
    
    async def test_health_check(self, db):
        """Test health check functionality"""
        health = await db.health_check()
        
        assert health["postgresql"] is True
        assert health["redis"] is True
        # Neo4j might be False if not running
    
    async def test_pool_status(self, db):
        """Test connection pool status reporting"""
        # Run some queries first to ensure counters are > 0
        await db.execute_query("SELECT 1")
        await db.redis_execute("ping")
        
        status = db.get_pool_status()
        
        # PostgreSQL pool status
        assert status["postgresql"]["initialized"] is True
        assert status["postgresql"]["min_size"] >= 10
        assert status["postgresql"]["max_size"] >= 20
        assert status["postgresql"]["queries"] > 0  # We've run queries
        
        # Redis status
        assert status["redis"]["initialized"] is True
        assert status["redis"]["commands"] > 0  # We've run commands
    
    async def test_slow_query_tracking(self, db):
        """Test that slow queries are tracked"""
        initial_slow_count = len(db.metrics["slow_queries"])
        
        # Run a slow query (1.1 seconds)
        await db.execute_query(
            "SELECT pg_sleep(1.1)",
            fetch_one=True
        )
        
        # Check that slow query was tracked
        assert len(db.metrics["slow_queries"]) > initial_slow_count
        slow_query = db.metrics["slow_queries"][-1]
        assert slow_query["type"] == "postgresql"
        assert slow_query["time"] > 1.0
    
    async def test_error_metrics(self, db):
        """Test that errors are tracked in metrics"""
        initial_errors = db.metrics["pg_errors"]
        
        # Try an invalid query
        with pytest.raises(Exception):
            await db.execute_query("SELECT * FROM nonexistent_table")
        
        # Verify error was tracked
        assert db.metrics["pg_errors"] == initial_errors + 1


@pytest.mark.integration
class TestQueryBuilderIntegration:
    """Test query builder with real database"""
    
    async def test_insert_and_select(self, pg_conn):
        """Test INSERT and SELECT operations"""
        # Insert test data
        data = {
            "server_name": "TEST_QUERY_BUILDER",
            "server_type": "test",
            "is_deployed": False
        }
        
        query, values = QueryBuilder.insert("mcp_servers", data)
        result = await pg_conn.fetchrow(query, *values)
        
        assert result["server_name"] == "TEST_QUERY_BUILDER"
        server_id = result["id"]
        
        # Select the data back
        query, values = QueryBuilder.select(
            "mcp_servers",
            conditions={"id": server_id}
        )
        result = await pg_conn.fetchrow(query, *values)
        
        assert result["server_name"] == "TEST_QUERY_BUILDER"
        assert result["is_deployed"] is False
        
        # Clean up
        await pg_conn.execute(
            "DELETE FROM orchestrator.mcp_servers WHERE id = $1",
            server_id
        )
    
    async def test_update_operation(self, pg_conn):
        """Test UPDATE operation"""
        # Insert test data - use persona_instances which has updated_at
        persona_type_result = await pg_conn.fetchrow("""
            SELECT id FROM orchestrator.persona_types LIMIT 1
        """)
        
        result = await pg_conn.fetchrow("""
            INSERT INTO orchestrator.persona_instances 
            (instance_name, persona_type_id, azure_devops_project, is_active)
            VALUES ($1, $2, $3, $4)
            RETURNING id, is_active
        """, "TEST_UPDATE_PERSONA", persona_type_result["id"], "test-project", False)
        
        instance_id = result["id"]
        assert result["is_active"] is False
        
        # Update the data
        update_data = {"is_active": True}
        conditions = {"id": instance_id}
        
        query, values = QueryBuilder.update(
            "persona_instances",
            update_data,
            conditions
        )
        result = await pg_conn.fetchrow(query, *values)
        
        assert result["is_active"] is True
        assert result["updated_at"] is not None
        
        # Clean up
        await pg_conn.execute(
            "DELETE FROM orchestrator.persona_instances WHERE id = $1",
            instance_id
        )