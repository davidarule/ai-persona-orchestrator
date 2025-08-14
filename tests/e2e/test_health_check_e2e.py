"""
End-to-end tests for health check endpoints
"""

import pytest
import httpx
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.api.server import app


@pytest.mark.e2e
class TestHealthCheckE2E:
    """E2E tests for health check endpoints"""
    
    @pytest.fixture
    async def client(self):
        """Create test client"""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    
    @pytest.mark.asyncio
    async def test_basic_health_check(self, client):
        """Test basic health endpoint"""
        response = await client.get("/api/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
    
    @pytest.mark.asyncio
    async def test_database_health_check(self, client):
        """Test comprehensive database health check"""
        response = await client.get("/api/health/database")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check overall status
        assert data["status"] in ["healthy", "degraded"]
        assert "timestamp" in data
        
        # Check database statuses
        assert "databases" in data
        # In test environment, databases might not be initialized yet
        assert isinstance(data["databases"]["postgresql"], bool)
        assert isinstance(data["databases"]["redis"], bool)
        # Neo4j might be False
        
        # Check connection pool info
        assert "connection_pools" in data
        pool_status = data["connection_pools"]["postgresql"]
        assert "initialized" in pool_status
        assert "min_size" in pool_status
        assert "max_size" in pool_status
        
        # If database is connected, check table counts
        if data["databases"]["postgresql"]:
            assert "table_counts" in data
            assert data["table_counts"]["workflow_definitions"] >= 43
            assert data["table_counts"]["persona_types"] >= 25
            assert data["table_counts"]["persona_instances"] >= 0
            assert data["table_counts"]["mcp_servers"] >= 8
        
        # Check configuration details
        assert "details" in data
        assert data["details"]["postgresql_port"] == 5434
    
    @pytest.mark.asyncio
    async def test_detailed_health_check(self, client):
        """Test detailed system health check"""
        response = await client.get("/api/health/detailed")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] in ["healthy", "degraded"]
        assert "timestamp" in data
        assert "components" in data
        
        # Check API component
        assert data["components"]["api"]["status"] == "healthy"
        assert data["components"]["api"]["version"] == "1.0.0"
        
        # Check databases component
        assert "databases" in data["components"]
        db_component = data["components"]["databases"]
        assert db_component["status"] in ["healthy", "degraded"]
        
        # Check websocket component
        assert data["components"]["websocket"]["status"] == "healthy"
        assert "active_connections" in data["components"]["websocket"]
    
    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self):
        """Test concurrent health check requests"""
        from httpx import AsyncClient
        transport = httpx.ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Make 10 concurrent requests
            tasks = []
            for _ in range(10):
                task = client.get("/api/health/database")
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks)
            
            # All should succeed
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert data["status"] in ["healthy", "degraded"]
    
    @pytest.mark.asyncio
    async def test_health_check_performance(self, client):
        """Test health check endpoint performance"""
        import time
        
        # Basic health check should be fast
        start = time.time()
        response = await client.get("/api/health")
        basic_time = time.time() - start
        
        assert response.status_code == 200
        assert basic_time < 0.1  # Should complete in under 100ms
        
        # Database health check might take longer
        start = time.time()
        response = await client.get("/api/health/database")
        db_time = time.time() - start
        
        assert response.status_code == 200
        assert db_time < 1.0  # Should complete in under 1 second
    
    @pytest.mark.asyncio
    async def test_health_check_with_database_issue(self, client, monkeypatch):
        """Test health check when database has issues"""
        # This would require mocking the database connection
        # For now, we just verify the endpoint handles errors gracefully
        response = await client.get("/api/health/database")
        
        assert response.status_code == 200
        # Even with issues, endpoint should return a response
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]