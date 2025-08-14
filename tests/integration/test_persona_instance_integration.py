"""
Integration tests for PersonaInstance functionality
"""

import pytest
from uuid import uuid4
from decimal import Decimal

from backend.models.persona_instance import (
    PersonaInstance,
    PersonaInstanceCreate,
    PersonaInstanceUpdate,
    LLMProvider,
    LLMModel
)
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.persona_instance_service import PersonaInstanceService


@pytest.mark.integration
@pytest.mark.asyncio
class TestPersonaInstanceIntegration:
    """Integration tests for PersonaInstance with real database"""
    
    async def test_full_persona_instance_lifecycle(self, db, clean_test_data):
        """Test complete lifecycle of a persona instance"""
        # Create a persona type first
        type_repo = PersonaTypeRepository(db)
        persona_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"test-integration-type-{uuid4().hex[:8]}",
            display_name="Integration Test Type",
            category=PersonaCategory.DEVELOPMENT,
            description="Type for integration testing",
            base_workflow_id="test-workflow"
        ))
        
        service = PersonaInstanceService(db)
        
        # 1. Create instance
        instance_name = f"TEST_Integration_Instance_{uuid4().hex[:8]}"
        create_data = PersonaInstanceCreate(
            instance_name=instance_name,
            persona_type_id=persona_type.id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="IntegrationTest",
            repository_name="test-repo",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    temperature=0.7,
                    api_key_env_var="OPENAI_API_KEY"
                ),
                LLMModel(
                    provider=LLMProvider.ANTHROPIC,
                    model_name="claude-3",
                    temperature=0.5,
                    api_key_env_var="ANTHROPIC_API_KEY"
                )
            ],
            spend_limit_daily=Decimal("100.00"),
            spend_limit_monthly=Decimal("2000.00"),
            max_concurrent_tasks=10,
            priority_level=5,
            custom_settings={"env": "test", "features": ["code_review", "testing"]}
        )
        
        instance = await service.create_instance(create_data)
        
        # Verify creation
        assert instance is not None
        assert instance.id is not None
        assert instance.instance_name == instance_name
        assert len(instance.llm_providers) == 2
        assert instance.spend_limit_daily == Decimal("100.00")
        assert instance.persona_type_name == persona_type.type_name
        assert instance.available_capacity == 10
        
        # 2. Retrieve instance
        retrieved = await service.get_instance(instance.id)
        assert retrieved is not None
        assert retrieved.id == instance.id
        assert retrieved.persona_display_name == "Integration Test Type"
        
        # 3. Update instance
        update_data = PersonaInstanceUpdate(
            max_concurrent_tasks=15,
            priority_level=8,
            custom_settings={"env": "test", "features": ["code_review", "testing", "deployment"]}
        )
        
        updated = await service.update_instance(instance.id, update_data)
        assert updated is not None
        assert updated.max_concurrent_tasks == 15
        assert updated.priority_level == 8
        assert len(updated.custom_settings["features"]) == 3
        
        # 4. Record spend
        await service.record_spend(instance.id, Decimal("25.50"), "gpt-4 api call")
        
        # Check spend was recorded
        after_spend = await service.get_instance(instance.id)
        assert after_spend.current_spend_daily == Decimal("25.50")
        assert after_spend.current_spend_monthly == Decimal("25.50")
        assert after_spend.spend_percentage_daily == 25.5
        
        # 5. Find available instance
        available = await service.find_available_instance(persona_type.id, "IntegrationTest")
        assert available is not None
        assert available.id == instance.id
        assert available.available_capacity > 0
        
        # 6. Test spend limits
        # Add more spend to exceed daily limit
        await service.record_spend(instance.id, Decimal("80.00"), "large operation")
        
        # Should not be available anymore due to spend limit
        available_after_limit = await service.find_available_instance(persona_type.id, "IntegrationTest")
        assert available_after_limit is None
        
        # 7. Deactivate instance
        success = await service.deactivate_instance(instance.id)
        assert success is True
        
        # Verify deactivation
        deactivated = await service.get_instance(instance.id)
        assert deactivated.is_active is False
        
        # Clean up
        await db.execute_query(
            "DELETE FROM orchestrator.persona_instances WHERE id = $1",
            instance.id
        )
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            persona_type.id
        )
    
    async def test_multiple_instances_same_type(self, db, clean_test_data):
        """Test managing multiple instances of the same persona type"""
        # Create a persona type
        type_repo = PersonaTypeRepository(db)
        persona_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"test-multi-instance-{uuid4().hex[:8]}",
            display_name="Multi Instance Test",
            category=PersonaCategory.DEVELOPMENT,
            description="Type for testing multiple instances",
            base_workflow_id="test-workflow"
        ))
        
        service = PersonaInstanceService(db)
        instances = []
        
        # Create 3 instances for different projects
        projects = ["ProjectA", "ProjectB", "ProjectC"]
        for i, project in enumerate(projects):
            instance = await service.create_instance(PersonaInstanceCreate(
                instance_name=f"TEST_Multi_{project}_{uuid4().hex[:8]}",
                persona_type_id=persona_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project=project,
                llm_providers=[
                    LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name="gpt-4",
                        api_key_env_var="OPENAI_API_KEY"
                    )
                ],
                max_concurrent_tasks=5,
                priority_level=i  # Different priorities
            ))
            instances.append(instance)
        
        # Get all instances of this type
        type_instances = await service.get_instances_by_type(persona_type.id)
        assert len(type_instances) == 3
        
        # Record different spend amounts
        await service.record_spend(instances[0].id, Decimal("30.00"), "op1")
        await service.record_spend(instances[1].id, Decimal("45.00"), "op2")
        await service.record_spend(instances[2].id, Decimal("20.00"), "op3")
        
        # Get statistics
        stats = await service.get_instance_statistics()
        assert stats["total_instances"] >= 3
        assert stats["active_instances"] >= 3
        # Stats use type_name not display_name
        assert persona_type.type_name in stats["by_type"]
        assert stats["by_type"][persona_type.type_name] >= 3
        assert stats["total_daily_spend"] >= Decimal("95.00")
        
        # Find best available instance (should be instance[2] with lowest spend)
        available = await service.find_available_instance(persona_type.id)
        assert available is not None
        # Should pick one with capacity and no spend limit exceeded
        
        # Clean up
        for instance in instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance.id
            )
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            persona_type.id
        )
    
    async def test_concurrent_instance_operations(self, db, clean_test_data):
        """Test concurrent operations on persona instances"""
        import asyncio
        
        # Create a persona type
        type_repo = PersonaTypeRepository(db)
        persona_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"test-concurrent-{uuid4().hex[:8]}",
            display_name="Concurrent Test",
            category=PersonaCategory.TESTING,
            description="Type for concurrent testing",
            base_workflow_id="test-workflow"
        ))
        
        service = PersonaInstanceService(db)
        
        # Create instance
        instance = await service.create_instance(PersonaInstanceCreate(
            instance_name=f"TEST_Concurrent_{uuid4().hex[:8]}",
            persona_type_id=persona_type.id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="ConcurrentTest",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ],
            spend_limit_daily=Decimal("500.00")
        ))
        
        # Simulate concurrent spend updates
        async def record_spend(amount: Decimal, operation: str):
            await service.record_spend(instance.id, amount, operation)
        
        # Run 5 concurrent spend updates
        tasks = [
            record_spend(Decimal("10.00"), f"op{i}")
            for i in range(5)
        ]
        
        await asyncio.gather(*tasks)
        
        # Check final spend
        final_instance = await service.get_instance(instance.id)
        assert final_instance.current_spend_daily == Decimal("50.00")
        assert final_instance.spend_percentage_daily == 10.0
        
        # Clean up
        await db.execute_query(
            "DELETE FROM orchestrator.persona_instances WHERE id = $1",
            instance.id
        )
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            persona_type.id
        )