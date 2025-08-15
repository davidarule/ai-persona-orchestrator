"""
Integration tests for Persona Instance API with real database
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime
from decimal import Decimal
from httpx import AsyncClient

from backend.api.server import app
from backend.services.database import DatabaseManager
from backend.models.persona_instance import LLMProvider, LLMModel


@pytest.mark.asyncio
class TestPersonaInstanceAPIIntegration:
    """Integration tests for persona instance API with real database"""
    
    @pytest.fixture
    async def client(self):
        """Create async test client"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac
    
    @pytest.fixture
    async def db(self):
        """Create database connection"""
        db_manager = DatabaseManager()
        await db_manager.initialize()
        yield db_manager
        await db_manager.close()
    
    @pytest.fixture
    async def test_persona_type(self, db):
        """Create a test persona type"""
        query = """
        INSERT INTO orchestrator.persona_types (
            type_name, display_name, base_workflow_id, 
            description, capabilities, default_llm_config
        ) VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """
        
        result = await db.execute_query(
            query,
            f"test-developer-{uuid4().hex[:8]}",
            "Test Developer",
            "wf0",
            "Test developer persona",
            ["coding", "testing"],
            {
                "providers": [{
                    "provider": "openai",
                    "model_name": "gpt-4",
                    "temperature": 0.7
                }]
            },
            fetch_one=True
        )
        
        persona_type_id = result["id"]
        yield persona_type_id
        
        # Cleanup
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            persona_type_id
        )
    
    async def test_full_instance_lifecycle(self, client, test_persona_type):
        """Test complete lifecycle: create, update, use, delete"""
        # 1. Create instance
        create_data = {
            "instance_name": f"Integration Test Bot {uuid4().hex[:8]}",
            "persona_type_id": str(test_persona_type),
            "azure_devops_org": "https://dev.azure.com/aitest",
            "azure_devops_project": "AI-Personas-Test-Sandbox-2",
            "llm_providers": [
                {
                    "provider": "openai",
                    "model_name": "gpt-4",
                    "temperature": 0.7,
                    "api_key_env_var": "OPENAI_API_KEY"
                },
                {
                    "provider": "anthropic",
                    "model_name": "claude-3-opus-20240229",
                    "temperature": 0.5,
                    "api_key_env_var": "ANTHROPIC_API_KEY"
                }
            ],
            "spend_limit_daily": "100.00",
            "spend_limit_monthly": "2000.00",
            "max_concurrent_tasks": 10,
            "priority_level": 5
        }
        
        response = await client.post("/api/v1/persona-instances/", json=create_data)
        assert response.status_code == 200
        
        instance = response.json()
        instance_id = instance["id"]
        assert instance["instance_name"] == create_data["instance_name"]
        assert len(instance["llm_providers"]) == 2
        assert instance["spend_limit_daily"] == 100.0
        assert instance["is_active"] is True
        
        # 2. Get instance
        response = await client.get(f"/api/v1/persona-instances/{instance_id}")
        assert response.status_code == 200
        fetched = response.json()
        assert fetched["id"] == instance_id
        
        # 3. Update instance
        update_data = {
            "instance_name": "Updated Integration Bot",
            "spend_limit_daily": "150.00",
            "priority_level": 8
        }
        
        response = await client.patch(
            f"/api/v1/persona-instances/{instance_id}",
            json=update_data
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["instance_name"] == "Updated Integration Bot"
        assert updated["spend_limit_daily"] == 150.0
        assert updated["priority_level"] == 8
        
        # 4. Deactivate instance
        response = await client.post(f"/api/v1/persona-instances/{instance_id}/deactivate")
        assert response.status_code == 200
        deactivated = response.json()
        assert deactivated["is_active"] is False
        
        # 5. Reactivate instance
        response = await client.post(f"/api/v1/persona-instances/{instance_id}/activate")
        assert response.status_code == 200
        activated = response.json()
        assert activated["is_active"] is True
        
        # 6. Get spend status
        response = await client.get(f"/api/v1/persona-instances/{instance_id}/spend/status")
        assert response.status_code == 200
        spend_status = response.json()
        assert spend_status["daily_spent"] == 0.0
        assert spend_status["daily_limit"] == 150.0
        assert spend_status["daily_exceeded"] is False
        
        # 7. Record some spend
        response = await client.post(
            f"/api/v1/persona-instances/{instance_id}/spend/record",
            json={
                "amount": "25.50",
                "description": "Integration test LLM usage"
            }
        )
        assert response.status_code == 200
        
        # 8. Check spend history
        response = await client.get(f"/api/v1/persona-instances/{instance_id}/spend/history")
        assert response.status_code == 200
        history = response.json()
        assert len(history["history"]) > 0
        assert float(history["total_spend"]) == 25.50
        
        # 9. Delete instance
        response = await client.delete(f"/api/v1/persona-instances/{instance_id}")
        assert response.status_code == 200
        
        # 10. Verify deletion
        response = await client.get(f"/api/v1/persona-instances/{instance_id}")
        assert response.status_code == 404
    
    async def test_list_instances_with_filters(self, client, test_persona_type):
        """Test listing instances with various filters"""
        # Create multiple instances
        instances = []
        for i in range(5):
            create_data = {
                "instance_name": f"Filter Test Bot {i}",
                "persona_type_id": str(test_persona_type),
                "azure_devops_org": "https://dev.azure.com/aitest",
                "azure_devops_project": f"Project-{i % 2}",  # Two different projects
                "llm_providers": [{
                    "provider": "openai",
                    "model_name": "gpt-3.5-turbo",
                    "api_key_env_var": "OPENAI_API_KEY"
                }],
                "is_active": i % 2 == 0  # Alternate active/inactive
            }
            
            response = await client.post("/api/v1/persona-instances/", json=create_data)
            assert response.status_code == 200
            instances.append(response.json()["id"])
        
        # Test filter by active status
        response = await client.get("/api/v1/persona-instances/?is_active=true")
        assert response.status_code == 200
        data = response.json()
        assert all(inst["is_active"] for inst in data["instances"])
        
        # Test filter by project
        response = await client.get("/api/v1/persona-instances/?project=Project-0")
        assert response.status_code == 200
        data = response.json()
        assert all(inst["azure_devops_project"] == "Project-0" for inst in data["instances"])
        
        # Test filter by persona type
        response = await client.get(f"/api/v1/persona-instances/?persona_type_id={test_persona_type}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["instances"]) >= 5
        
        # Test pagination
        response = await client.get("/api/v1/persona-instances/?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["page_size"] == 2
        assert len(data["instances"]) <= 2
        
        # Cleanup
        for instance_id in instances:
            await client.delete(f"/api/v1/persona-instances/{instance_id}")
    
    async def test_team_creation(self, client, db):
        """Test creating a development team"""
        # Create required persona types
        persona_types = {}
        for role in ["software-architect", "senior-developer", "qa-engineer"]:
            query = """
            INSERT INTO orchestrator.persona_types (
                type_name, display_name, base_workflow_id
            ) VALUES ($1, $2, $3)
            RETURNING id
            """
            result = await db.execute_query(
                query,
                f"{role}-{uuid4().hex[:8]}",
                role.replace("-", " ").title(),
                "wf0",
                fetch_one=True
            )
            persona_types[role] = result["id"]
        
        # Create team
        team_data = {
            "project_name": "Team Test Project",
            "azure_devops_org": "https://dev.azure.com/aitest",
            "azure_devops_project": "AI-Personas-Test-Sandbox-2",
            "team_size": "small"
        }
        
        response = await client.post("/api/v1/persona-instances/factory/team", json=team_data)
        assert response.status_code == 200
        
        team = response.json()
        assert len(team) >= 3  # At least 3 team members for small team
        
        # Verify each team member
        created_instances = []
        for role, instance in team.items():
            assert "id" in instance
            assert instance["azure_devops_project"] == "AI-Personas-Test-Sandbox-2"
            assert instance["is_active"] is True
            created_instances.append(instance["id"])
        
        # Cleanup
        for instance_id in created_instances:
            await client.delete(f"/api/v1/persona-instances/{instance_id}")
        
        for persona_type_id in persona_types.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_type_id
            )
    
    async def test_instance_cloning(self, client, test_persona_type):
        """Test cloning an existing instance"""
        # Create source instance
        source_data = {
            "instance_name": "Source Bot",
            "persona_type_id": str(test_persona_type),
            "azure_devops_org": "https://dev.azure.com/aitest",
            "azure_devops_project": "Source Project",
            "repository_name": "source-repo",
            "llm_providers": [{
                "provider": "openai",
                "model_name": "gpt-4",
                "temperature": 0.8,
                "max_tokens": 2000,
                "api_key_env_var": "OPENAI_API_KEY"
            }],
            "spend_limit_daily": "75.00",
            "max_concurrent_tasks": 7,
            "priority_level": 3,
            "custom_settings": {"test_setting": "test_value"}
        }
        
        response = await client.post("/api/v1/persona-instances/", json=source_data)
        assert response.status_code == 200
        source_instance = response.json()
        
        # Clone instance
        clone_data = {
            "new_instance_name": "Cloned Bot",
            "new_project": "Target Project",
            "new_repository": "target-repo"
        }
        
        response = await client.post(
            f"/api/v1/persona-instances/{source_instance['id']}/clone",
            json=clone_data
        )
        assert response.status_code == 200
        
        cloned = response.json()
        assert cloned["id"] != source_instance["id"]
        assert cloned["instance_name"] == "Cloned Bot"
        assert cloned["azure_devops_project"] == "Target Project"
        assert cloned["repository_name"] == "target-repo"
        
        # Verify settings were copied
        assert cloned["spend_limit_daily"] == source_instance["spend_limit_daily"]
        assert cloned["max_concurrent_tasks"] == source_instance["max_concurrent_tasks"]
        assert cloned["priority_level"] == source_instance["priority_level"]
        assert cloned["custom_settings"] == source_instance["custom_settings"]
        assert len(cloned["llm_providers"]) == len(source_instance["llm_providers"])
        
        # Cleanup
        await client.delete(f"/api/v1/persona-instances/{source_instance['id']}")
        await client.delete(f"/api/v1/persona-instances/{cloned['id']}")
    
    async def test_analytics_endpoint(self, client, test_persona_type):
        """Test analytics summary endpoint"""
        # Create instances with spend data
        instances = []
        for i in range(3):
            create_data = {
                "instance_name": f"Analytics Test Bot {i}",
                "persona_type_id": str(test_persona_type),
                "azure_devops_org": "https://dev.azure.com/aitest",
                "azure_devops_project": "Analytics Project",
                "llm_providers": [{
                    "provider": "openai",
                    "model_name": "gpt-3.5-turbo",
                    "api_key_env_var": "OPENAI_API_KEY"
                }],
                "spend_limit_daily": "50.00",
                "spend_limit_monthly": "1000.00"
            }
            
            response = await client.post("/api/v1/persona-instances/", json=create_data)
            assert response.status_code == 200
            instance = response.json()
            instances.append(instance["id"])
            
            # Record some spend
            await client.post(
                f"/api/v1/persona-instances/{instance['id']}/spend/record",
                json={
                    "amount": str(10 * (i + 1)),
                    "description": f"Analytics test spend {i}"
                }
            )
        
        # Get analytics
        response = await client.get(
            "/api/v1/persona-instances/analytics/summary?project=Analytics Project"
        )
        assert response.status_code == 200
        
        analytics = response.json()
        assert "instance_stats" in analytics
        assert "spend_analytics" in analytics
        
        # Verify spend analytics
        spend_summary = analytics["spend_analytics"]["summary"]
        assert spend_summary["instance_count"] >= 3
        assert spend_summary["total_daily_spend"] >= 60.0  # 10 + 20 + 30
        
        # Cleanup
        for instance_id in instances:
            await client.delete(f"/api/v1/persona-instances/{instance_id}")
    
    async def test_concurrent_operations(self, client, test_persona_type):
        """Test handling concurrent API operations"""
        # Create an instance
        create_data = {
            "instance_name": "Concurrent Test Bot",
            "persona_type_id": str(test_persona_type),
            "azure_devops_org": "https://dev.azure.com/aitest",
            "azure_devops_project": "Concurrent Project",
            "llm_providers": [{
                "provider": "openai",
                "model_name": "gpt-3.5-turbo",
                "api_key_env_var": "OPENAI_API_KEY"
            }]
        }
        
        response = await client.post("/api/v1/persona-instances/", json=create_data)
        assert response.status_code == 200
        instance_id = response.json()["id"]
        
        # Perform concurrent spend recordings
        async def record_spend(index):
            return await client.post(
                f"/api/v1/persona-instances/{instance_id}/spend/record",
                json={
                    "amount": "1.00",
                    "description": f"Concurrent spend {index}"
                }
            )
        
        # Run 10 concurrent spend recordings
        tasks = [record_spend(i) for i in range(10)]
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(r.status_code == 200 for r in responses)
        
        # Verify total spend
        response = await client.get(f"/api/v1/persona-instances/{instance_id}/spend/status")
        assert response.status_code == 200
        spend_status = response.json()
        assert spend_status["daily_spent"] >= 10.0
        
        # Cleanup
        await client.delete(f"/api/v1/persona-instances/{instance_id}")
    
    async def test_error_handling(self, client):
        """Test various error scenarios"""
        # Test 404 for non-existent instance
        fake_id = str(uuid4())
        response = await client.get(f"/api/v1/persona-instances/{fake_id}")
        assert response.status_code == 404
        
        # Test validation errors
        invalid_data = {
            "instance_name": "x" * 300,  # Too long
            "persona_type_id": "not-a-uuid",
            "azure_devops_org": "",
            "azure_devops_project": "",
            "llm_providers": []
        }
        
        response = await client.post("/api/v1/persona-instances/", json=invalid_data)
        assert response.status_code == 422
        
        # Test invalid UUID format
        response = await client.get("/api/v1/persona-instances/not-a-uuid")
        assert response.status_code == 422
        
        # Test invalid team size
        team_data = {
            "project_name": "Test",
            "azure_devops_org": "https://dev.azure.com/test",
            "azure_devops_project": "Test",
            "team_size": "extra-large"  # Invalid
        }
        
        response = await client.post("/api/v1/persona-instances/factory/team", json=team_data)
        assert response.status_code == 422