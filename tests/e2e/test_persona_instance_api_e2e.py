"""
End-to-End tests for Persona Instance API simulating real-world scenarios
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal
from httpx import AsyncClient
import os

from backend.api.server import app
from backend.services.database import DatabaseManager
from backend.models.persona_instance import LLMProvider


@pytest.mark.e2e
@pytest.mark.asyncio
class TestPersonaInstanceAPIE2E:
    """E2E tests simulating real-world API usage patterns"""
    
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
    async def setup_persona_types(self, db):
        """Setup all required persona types for E2E tests"""
        persona_types = {}
        
        # Define persona types matching real system
        types_to_create = [
            ("software-architect", "Software Architect", "wf0"),
            ("senior-developer", "Senior Developer", "wf1"),
            ("qa-engineer", "QA Engineer", "wf2"),
            ("devops-engineer", "DevOps Engineer", "wf3"),
            ("security-architect", "Security Architect", "wf4"),
            ("scrum-master", "Scrum Master", "wf5")
        ]
        
        for type_name, display_name, workflow_id in types_to_create:
            query = """
            INSERT INTO orchestrator.persona_types (
                type_name, display_name, base_workflow_id,
                description, capabilities, default_llm_config
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """
            
            result = await db.execute_query(
                query,
                f"{type_name}-e2e-{uuid4().hex[:8]}",
                display_name,
                workflow_id,
                f"{display_name} for E2E testing",
                ["coding", "architecture", "testing"],
                {
                    "providers": [{
                        "provider": "openai",
                        "model_name": "gpt-4",
                        "temperature": 0.7,
                        "max_tokens": 4096
                    }]
                },
                fetch_one=True
            )
            persona_types[type_name] = result["id"]
        
        yield persona_types
        
        # Cleanup
        for persona_id in persona_types.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_id
            )
    
    async def test_real_world_project_setup(self, client, setup_persona_types):
        """Test setting up a complete project team as in real usage"""
        # Scenario: New project "AI Chat Assistant" needs a development team
        
        # 1. Create the development team
        team_request = {
            "project_name": "AI Chat Assistant",
            "azure_devops_org": "https://dev.azure.com/aitest",
            "azure_devops_project": "AI-Personas-Test-Sandbox-2",
            "team_size": "medium",
            "custom_settings": {
                "project_phase": "initial_development",
                "expected_duration_months": 6,
                "technology_stack": ["Python", "FastAPI", "React", "PostgreSQL"]
            }
        }
        
        response = await client.post("/api/v1/persona-instances/factory/team", json=team_request)
        assert response.status_code == 200
        
        team = response.json()
        print(f"Created team with {len(team)} members")
        
        # 2. Verify team composition
        expected_roles = ["architect", "lead_developer", "qa_engineer"]
        for role in expected_roles:
            assert role in team, f"Missing {role} in team"
            assert team[role]["is_active"] is True
        
        # 3. Configure specific LLM providers for each role
        # Architect gets more powerful model
        architect_update = {
            "llm_providers": [
                {
                    "provider": "openai",
                    "model_name": "gpt-4-turbo-preview",
                    "temperature": 0.3,
                    "max_tokens": 8192,
                    "api_key_env_var": "OPENAI_API_KEY"
                },
                {
                    "provider": "anthropic",
                    "model_name": "claude-3-opus-20240229",
                    "temperature": 0.2,
                    "api_key_env_var": "ANTHROPIC_API_KEY"
                }
            ],
            "spend_limit_daily": "150.00",
            "priority_level": 10
        }
        
        response = await client.patch(
            f"/api/v1/persona-instances/{team['architect']['id']}",
            json=architect_update
        )
        assert response.status_code == 200
        
        # 4. Set spend alerts for budget monitoring
        for role, instance in team.items():
            # Use spend tracking service through API
            response = await client.get(f"/api/v1/persona-instances/{instance['id']}/spend/status")
            assert response.status_code == 200
        
        # 5. Simulate first day of work
        work_items = [
            ("architect", "Design system architecture", "25.00"),
            ("lead_developer", "Set up project repository", "15.00"),
            ("qa_engineer", "Create test plan", "10.00")
        ]
        
        for role, task, cost in work_items:
            response = await client.post(
                f"/api/v1/persona-instances/{team[role]['id']}/spend/record",
                json={
                    "amount": cost,
                    "description": task
                }
            )
            assert response.status_code == 200
        
        # 6. Check project analytics
        response = await client.get(
            "/api/v1/persona-instances/analytics/summary?project=AI-Personas-Test-Sandbox-2"
        )
        assert response.status_code == 200
        
        analytics = response.json()
        assert analytics["spend_analytics"]["summary"]["total_daily_spend"] >= 50.0
        
        # Cleanup
        for instance in team.values():
            await client.delete(f"/api/v1/persona-instances/{instance['id']}")
    
    async def test_spend_limit_enforcement(self, client, setup_persona_types):
        """Test real-world spend limit scenarios and warnings"""
        # Create instance with low daily limit for testing
        instance_data = {
            "instance_name": "Budget Test Bot",
            "persona_type_id": str(setup_persona_types["qa-engineer"]),
            "azure_devops_org": "https://dev.azure.com/aitest",
            "azure_devops_project": "AI-Personas-Test-Sandbox-2",
            "llm_providers": [{
                "provider": "openai",
                "model_name": "gpt-3.5-turbo",
                "api_key_env_var": "OPENAI_API_KEY"
            }],
            "spend_limit_daily": "10.00",  # Low limit for testing
            "spend_limit_monthly": "200.00"
        }
        
        response = await client.post("/api/v1/persona-instances/", json=instance_data)
        assert response.status_code == 200
        instance = response.json()
        
        # Simulate spend throughout the day
        spend_amounts = ["3.00", "3.00", "2.00", "1.50"]  # Total: 9.50
        
        for i, amount in enumerate(spend_amounts):
            response = await client.post(
                f"/api/v1/persona-instances/{instance['id']}/spend/record",
                json={
                    "amount": amount,
                    "description": f"Task {i+1}: Test execution"
                }
            )
            assert response.status_code == 200
            
            result = response.json()
            
            # Check if we're getting close to limit
            if i >= 2:  # After 8.00 spent (80%)
                status_response = await client.get(
                    f"/api/v1/persona-instances/{instance['id']}/spend/status"
                )
                status = status_response.json()
                assert status["daily_percentage"] > 80.0
        
        # Try to exceed limit
        response = await client.post(
            f"/api/v1/persona-instances/{instance['id']}/spend/record",
            json={
                "amount": "2.00",  # This would exceed daily limit
                "description": "Task that exceeds budget"
            }
        )
        assert response.status_code == 200
        
        # Check final status
        response = await client.get(f"/api/v1/persona-instances/{instance['id']}/spend/status")
        final_status = response.json()
        assert final_status["daily_exceeded"] is True
        
        # Cleanup
        await client.delete(f"/api/v1/persona-instances/{instance['id']}")
    
    async def test_api_performance_under_load(self, client, setup_persona_types):
        """Test API performance with multiple concurrent requests"""
        # Create base instance for load testing
        instance_data = {
            "instance_name": "Load Test Bot",
            "persona_type_id": str(setup_persona_types["senior-developer"]),
            "azure_devops_org": "https://dev.azure.com/aitest",
            "azure_devops_project": "AI-Personas-Test-Sandbox-2",
            "llm_providers": [{
                "provider": "openai",
                "model_name": "gpt-3.5-turbo",
                "api_key_env_var": "OPENAI_API_KEY"
            }]
        }
        
        response = await client.post("/api/v1/persona-instances/", json=instance_data)
        assert response.status_code == 200
        instance_id = response.json()["id"]
        
        # Define concurrent operations
        async def read_operation():
            return await client.get(f"/api/v1/persona-instances/{instance_id}")
        
        async def list_operation():
            return await client.get("/api/v1/persona-instances/?page_size=10")
        
        async def spend_operation():
            return await client.get(f"/api/v1/persona-instances/{instance_id}/spend/status")
        
        async def update_operation():
            return await client.patch(
                f"/api/v1/persona-instances/{instance_id}",
                json={"priority_level": 5}
            )
        
        # Run mixed operations concurrently
        operations = []
        for _ in range(5):
            operations.extend([
                read_operation(),
                list_operation(),
                spend_operation(),
                update_operation()
            ])
        
        start_time = datetime.utcnow()
        results = await asyncio.gather(*operations, return_exceptions=True)
        end_time = datetime.utcnow()
        
        # Verify results
        successful = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 200)
        duration = (end_time - start_time).total_seconds()
        
        print(f"\nLoad test results:")
        print(f"Total operations: {len(operations)}")
        print(f"Successful: {successful}")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Ops/second: {len(operations) / duration:.2f}")
        
        assert successful >= len(operations) * 0.95  # At least 95% success rate
        assert duration < 10  # Should complete within 10 seconds
        
        # Cleanup
        await client.delete(f"/api/v1/persona-instances/{instance_id}")
    
    async def test_multi_environment_deployment(self, client, setup_persona_types):
        """Test deploying same personas across dev/staging/prod environments"""
        environments = ["development", "staging", "production"]
        created_instances = []
        
        # 1. Create base instance for development
        base_instance_data = {
            "instance_name": "API Service Bot - Dev",
            "persona_type_id": str(setup_persona_types["senior-developer"]),
            "azure_devops_org": "https://dev.azure.com/aitest",
            "azure_devops_project": "AI-Personas-Test-Sandbox-2",
            "repository_name": "api-service",
            "llm_providers": [{
                "provider": "openai",
                "model_name": "gpt-4",
                "temperature": 0.5,
                "api_key_env_var": "OPENAI_API_KEY"
            }],
            "spend_limit_daily": "75.00",
            "spend_limit_monthly": "1500.00",
            "custom_settings": {
                "environment": "development",
                "deployment_branch": "develop",
                "auto_deploy": True
            }
        }
        
        response = await client.post("/api/v1/persona-instances/", json=base_instance_data)
        assert response.status_code == 200
        dev_instance = response.json()
        created_instances.append(dev_instance["id"])
        
        # 2. Clone for staging and production
        for env in ["staging", "production"]:
            clone_data = {
                "new_instance_name": f"API Service Bot - {env.capitalize()}",
                "new_project": "AI-Personas-Test-Sandbox-2",
                "new_repository": "api-service"
            }
            
            response = await client.post(
                f"/api/v1/persona-instances/{dev_instance['id']}/clone",
                json=clone_data
            )
            assert response.status_code == 200
            cloned = response.json()
            created_instances.append(cloned["id"])
            
            # Update environment-specific settings
            env_settings = {
                "custom_settings": {
                    "environment": env,
                    "deployment_branch": "main" if env == "production" else env,
                    "auto_deploy": env != "production",
                    "approval_required": env == "production"
                }
            }
            
            if env == "production":
                env_settings["spend_limit_daily"] = "200.00"
                env_settings["spend_limit_monthly"] = "4000.00"
                env_settings["priority_level"] = 10
            
            response = await client.patch(
                f"/api/v1/persona-instances/{cloned['id']}",
                json=env_settings
            )
            assert response.status_code == 200
        
        # 3. Verify all environments are set up
        response = await client.get(
            "/api/v1/persona-instances/?project=AI-Personas-Test-Sandbox-2"
        )
        assert response.status_code == 200
        
        instances = response.json()["instances"]
        env_instances = [i for i in instances if "API Service Bot" in i["instance_name"]]
        assert len(env_instances) >= 3
        
        # Cleanup
        for instance_id in created_instances:
            await client.delete(f"/api/v1/persona-instances/{instance_id}")
    
    async def test_incident_response_scenario(self, client, setup_persona_types):
        """Test rapid deployment of personas for incident response"""
        # Scenario: Production incident requires immediate response team
        
        incident_id = f"INC-{uuid4().hex[:8]}"
        response_team = []
        
        # 1. Deploy incident response team
        critical_roles = [
            ("devops-engineer", "Incident Commander", "200.00"),
            ("senior-developer", "Debug Specialist", "150.00"),
            ("security-architect", "Security Analyst", "150.00")
        ]
        
        for role, title, daily_limit in critical_roles:
            instance_data = {
                "instance_name": f"{incident_id} - {title}",
                "persona_type_id": str(setup_persona_types[role]),
                "azure_devops_org": "https://dev.azure.com/aitest",
                "azure_devops_project": "AI-Personas-Test-Sandbox-2",
                "llm_providers": [
                    {
                        "provider": "openai",
                        "model_name": "gpt-4-turbo-preview",
                        "temperature": 0.1,  # Low temperature for accuracy
                        "api_key_env_var": "OPENAI_API_KEY"
                    }
                ],
                "spend_limit_daily": daily_limit,
                "spend_limit_monthly": "5000.00",  # High monthly limit for incidents
                "priority_level": 10,  # Maximum priority
                "max_concurrent_tasks": 20,  # High concurrency for rapid response
                "custom_settings": {
                    "incident_id": incident_id,
                    "incident_priority": "P1",
                    "auto_escalate": True,
                    "notify_on_completion": True
                }
            }
            
            response = await client.post("/api/v1/persona-instances/", json=instance_data)
            assert response.status_code == 200
            instance = response.json()
            response_team.append(instance["id"])
        
        # 2. Simulate incident response activities
        activities = [
            ("Analyzing production logs", "45.00"),
            ("Identifying root cause", "35.00"),
            ("Implementing hotfix", "55.00"),
            ("Deploying fix to production", "25.00"),
            ("Post-incident analysis", "20.00")
        ]
        
        for activity, cost in activities:
            # Distribute work across team
            for i, instance_id in enumerate(response_team):
                individual_cost = float(cost) / len(response_team)
                response = await client.post(
                    f"/api/v1/persona-instances/{instance_id}/spend/record",
                    json={
                        "amount": str(individual_cost),
                        "description": f"{activity} - Part {i+1}"
                    }
                )
                assert response.status_code == 200
        
        # 3. Check incident response metrics
        response = await client.get("/api/v1/persona-instances/analytics/summary")
        assert response.status_code == 200
        
        # 4. After incident resolution, reduce capacity
        for instance_id in response_team:
            # Reduce limits back to normal
            response = await client.patch(
                f"/api/v1/persona-instances/{instance_id}",
                json={
                    "spend_limit_daily": "50.00",
                    "priority_level": 5,
                    "max_concurrent_tasks": 5
                }
            )
            assert response.status_code == 200
        
        # Cleanup
        for instance_id in response_team:
            await client.delete(f"/api/v1/persona-instances/{instance_id}")
    
    async def test_cost_optimization_workflow(self, client, setup_persona_types):
        """Test real-world cost optimization scenarios"""
        # Create instances with varying usage patterns
        instances = []
        usage_patterns = [
            ("High Usage Bot", "0.95", 50),  # 95% of limit
            ("Medium Usage Bot", "0.50", 30),  # 50% of limit
            ("Low Usage Bot", "0.10", 5),  # 10% of limit
            ("Idle Bot", "0.00", 0)  # No usage
        ]
        
        for name, usage_ratio, daily_spend in usage_patterns:
            instance_data = {
                "instance_name": name,
                "persona_type_id": str(setup_persona_types["senior-developer"]),
                "azure_devops_org": "https://dev.azure.com/aitest",
                "azure_devops_project": "Cost-Optimization-Test",
                "llm_providers": [{
                    "provider": "openai",
                    "model_name": "gpt-3.5-turbo",
                    "api_key_env_var": "OPENAI_API_KEY"
                }],
                "spend_limit_daily": "100.00",
                "spend_limit_monthly": "2000.00"
            }
            
            response = await client.post("/api/v1/persona-instances/", json=instance_data)
            assert response.status_code == 200
            instance = response.json()
            instances.append(instance["id"])
            
            # Simulate usage
            if daily_spend > 0:
                response = await client.post(
                    f"/api/v1/persona-instances/{instance['id']}/spend/record",
                    json={
                        "amount": str(daily_spend),
                        "description": f"Daily work - {usage_ratio} utilization"
                    }
                )
                assert response.status_code == 200
        
        # Get optimization recommendations
        response = await client.get(
            "/api/v1/persona-instances/?project=Cost-Optimization-Test"
        )
        assert response.status_code == 200
        
        project_instances = response.json()["instances"]
        
        # Apply optimizations based on usage
        for instance in project_instances:
            if "Idle" in instance["instance_name"]:
                # Deactivate idle instances
                response = await client.post(
                    f"/api/v1/persona-instances/{instance['id']}/deactivate"
                )
                assert response.status_code == 200
            elif "Low Usage" in instance["instance_name"]:
                # Reduce limits for low usage
                response = await client.patch(
                    f"/api/v1/persona-instances/{instance['id']}",
                    json={"spend_limit_daily": "25.00"}
                )
                assert response.status_code == 200
            elif "High Usage" in instance["instance_name"]:
                # Consider increasing limits for high usage
                response = await client.patch(
                    f"/api/v1/persona-instances/{instance['id']}",
                    json={"spend_limit_daily": "150.00"}
                )
                assert response.status_code == 200
        
        # Cleanup
        for instance_id in instances:
            await client.delete(f"/api/v1/persona-instances/{instance_id}")