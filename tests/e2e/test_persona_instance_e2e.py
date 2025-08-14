"""
End-to-end tests for PersonaInstance functionality
"""

import pytest
from uuid import uuid4
from decimal import Decimal
import asyncio

from backend.models.persona_instance import (
    PersonaInstanceCreate,
    PersonaInstanceUpdate,
    LLMProvider,
    LLMModel
)
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.repositories.persona_instance_repository import PersonaInstanceRepository
from backend.services.persona_instance_service import PersonaInstanceService


@pytest.mark.e2e
@pytest.mark.asyncio
class TestPersonaInstanceE2E:
    """End-to-end tests simulating real-world persona instance usage"""
    
    async def test_software_architect_persona_workflow(self, db, azure_devops_config, clean_test_data):
        """Test complete workflow for a Software Architect persona"""
        # Create Software Architect persona type
        type_repo = PersonaTypeRepository(db)
        architect_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"software-architect-e2e-{uuid4().hex[:8]}",
            display_name="Software Architect (E2E Test)",
            category=PersonaCategory.ARCHITECTURE,
            description="E2E test for Software Architect persona",
            base_workflow_id="wf0-feature-development",
            default_capabilities={
                "system_design": True,
                "code_review": True,
                "technical_documentation": True,
                "architecture_decisions": True
            }
        ))
        
        service = PersonaInstanceService(db)
        
        # Create Steve Bot instance for AI Orchestrator project
        steve_bot = await service.create_instance(PersonaInstanceCreate(
            instance_name=f"TEST_Steve_Bot_E2E_{uuid4().hex[:8]}",
            persona_type_id=architect_type.id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=azure_devops_config["test_project"],
            repository_name="ai-orchestrator",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4-turbo-preview",
                    temperature=0.7,
                    max_tokens=4096,
                    api_key_env_var="OPENAI_API_KEY"
                ),
                LLMModel(
                    provider=LLMProvider.ANTHROPIC,
                    model_name="claude-3-opus-20240229",
                    temperature=0.5,
                    api_key_env_var="ANTHROPIC_API_KEY"
                )
            ],
            spend_limit_daily=Decimal("100.00"),
            spend_limit_monthly=Decimal("2000.00"),
            max_concurrent_tasks=5,
            priority_level=10,  # High priority
            custom_settings={
                "code_style": "clean_architecture",
                "documentation_level": "comprehensive",
                "review_thoroughness": "high",
                "preferred_patterns": ["SOLID", "DDD", "CQRS"],
                "timezone": "UTC"
            }
        ))
        
        assert steve_bot is not None
        assert steve_bot.persona_display_name == "Software Architect (E2E Test)"
        assert steve_bot.priority_level == 10
        
        # Simulate daily operations
        operations = [
            ("System design review", Decimal("5.50")),
            ("Architecture documentation", Decimal("8.25")),
            ("Code review - PR #123", Decimal("3.75")),
            ("Technical consultation", Decimal("4.00")),
            ("Design pattern implementation", Decimal("6.00"))
        ]
        
        for operation, cost in operations:
            await service.record_spend(steve_bot.id, cost, operation)
            await asyncio.sleep(0.1)  # Simulate time between operations
        
        # Check current status
        current = await service.get_instance(steve_bot.id)
        assert current.current_spend_daily == Decimal("27.50")
        assert current.spend_percentage_daily == 27.5
        assert current.available_capacity == 5
        
        # Update configuration based on project needs
        await service.update_instance(steve_bot.id, PersonaInstanceUpdate(
            custom_settings={
                "code_style": "clean_architecture",
                "documentation_level": "comprehensive",
                "review_thoroughness": "high",
                "preferred_patterns": ["SOLID", "DDD", "CQRS", "Event Sourcing"],
                "timezone": "UTC",
                "focus_areas": ["microservices", "event-driven", "cloud-native"]
            }
        ))
        
        # Verify instance is still available for work
        available = await service.find_available_instance(
            architect_type.id,
            azure_devops_config["test_project"]
        )
        assert available is not None
        assert available.id == steve_bot.id
        
        # Clean up
        await db.execute_query(
            "DELETE FROM orchestrator.persona_instances WHERE id = $1",
            steve_bot.id
        )
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            architect_type.id
        )
    
    async def test_development_team_collaboration(self, db, azure_devops_config, clean_test_data):
        """Test multiple personas collaborating on a project"""
        type_repo = PersonaTypeRepository(db)
        service = PersonaInstanceService(db)
        
        # Create different persona types
        personas_config = [
            {
                "type_name": f"backend-dev-e2e-{uuid4().hex[:8]}",
                "display_name": "Backend Developer (E2E)",
                "category": PersonaCategory.DEVELOPMENT,
                "instance_name": f"TEST_Jordan_Bot_E2E_{uuid4().hex[:8]}",
                "llm_model": "gpt-4",
                "priority": 8
            },
            {
                "type_name": f"frontend-dev-e2e-{uuid4().hex[:8]}",
                "display_name": "Frontend Developer (E2E)",
                "category": PersonaCategory.DEVELOPMENT,
                "instance_name": f"TEST_Matt_Bot_E2E_{uuid4().hex[:8]}",
                "llm_model": "gpt-4",
                "priority": 8
            },
            {
                "type_name": f"qa-engineer-e2e-{uuid4().hex[:8]}",
                "display_name": "QA Engineer (E2E)",
                "category": PersonaCategory.TESTING,
                "instance_name": f"TEST_Kav_Bot_E2E_{uuid4().hex[:8]}",
                "llm_model": "gpt-3.5-turbo",
                "priority": 7
            }
        ]
        
        created_instances = []
        created_types = []
        
        # Create all persona types and instances
        for config in personas_config:
            # Create type
            persona_type = await type_repo.create(PersonaTypeCreate(
                type_name=config["type_name"],
                display_name=config["display_name"],
                category=config["category"],
                description=f"E2E test for {config['display_name']}",
                base_workflow_id="wf0-feature-development"
            ))
            created_types.append(persona_type)
            
            # Create instance
            instance = await service.create_instance(PersonaInstanceCreate(
                instance_name=config["instance_name"],
                persona_type_id=persona_type.id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=azure_devops_config["test_project"],
                repository_name="ai-orchestrator",
                llm_providers=[
                    LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name=config["llm_model"],
                        temperature=0.7,
                        api_key_env_var="OPENAI_API_KEY"
                    )
                ],
                spend_limit_daily=Decimal("50.00"),
                max_concurrent_tasks=3,
                priority_level=config["priority"]
            ))
            created_instances.append(instance)
        
        # Simulate collaborative work on a feature
        backend_instance, frontend_instance, qa_instance = created_instances
        
        # Backend development
        await service.record_spend(backend_instance.id, Decimal("8.50"), "API endpoint development")
        await service.record_spend(backend_instance.id, Decimal("4.25"), "Database schema design")
        
        # Frontend development
        await service.record_spend(frontend_instance.id, Decimal("6.00"), "UI component creation")
        await service.record_spend(frontend_instance.id, Decimal("3.50"), "State management setup")
        
        # QA testing
        await service.record_spend(qa_instance.id, Decimal("2.50"), "Test case design")
        await service.record_spend(qa_instance.id, Decimal("1.75"), "Integration test creation")
        
        # Get team statistics
        stats = await service.get_instance_statistics()
        assert stats["total_instances"] >= 3
        assert stats["total_daily_spend"] >= Decimal("26.50")
        
        # Verify all instances are still available
        for instance in created_instances:
            available = await service.find_available_instance(
                instance.persona_type_id,
                azure_devops_config["test_project"]
            )
            assert available is not None
        
        # Clean up
        for instance in created_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance.id
            )
        for persona_type in created_types:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_type.id
            )
    
    async def test_spend_limit_enforcement(self, db, test_persona_type_id, clean_test_data):
        """Test that spend limits are properly enforced"""
        service = PersonaInstanceService(db)
        
        # Create instance with low spend limit
        instance = await service.create_instance(PersonaInstanceCreate(
            instance_name=f"TEST_SpendLimit_E2E_{uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="SpendLimitTest",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ],
            spend_limit_daily=Decimal("20.00"),  # Low limit
            spend_limit_monthly=Decimal("400.00")
        ))
        
        # Gradually increase spend
        operations = [
            Decimal("5.00"),
            Decimal("7.50"),
            Decimal("6.00"),
            Decimal("3.50")  # This would exceed the $20 limit
        ]
        
        for i, amount in enumerate(operations):
            await service.record_spend(instance.id, amount, f"operation_{i}")
        
        # Check that limit was exceeded
        final = await service.get_instance(instance.id)
        assert final.current_spend_daily == Decimal("22.00")
        assert final.spend_percentage_daily == 110.0
        
        # Instance should not be available due to exceeded limit
        available = await service.find_available_instance(
            test_persona_type_id,
            "SpendLimitTest"
        )
        assert available is None
        
        # Test daily reset
        repo = PersonaInstanceRepository(db)
        reset_count = await repo.reset_daily_spend()
        assert reset_count >= 1
        
        # After reset, instance should be available again
        after_reset = await service.get_instance(instance.id)
        assert after_reset.current_spend_daily == Decimal("0.00")
        assert after_reset.current_spend_monthly == Decimal("22.00")  # Monthly not reset
        
        available_after_reset = await service.find_available_instance(
            test_persona_type_id,
            "SpendLimitTest"
        )
        assert available_after_reset is not None