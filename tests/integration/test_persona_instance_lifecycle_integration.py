"""
Integration tests for Persona Instance Lifecycle Service
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal

from backend.services.persona_instance_lifecycle import (
    PersonaInstanceLifecycle,
    InstanceState,
    InstanceHealthStatus
)
from backend.models.persona_instance import PersonaInstanceCreate, LLMProvider, LLMModel
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.persona_instance_service import PersonaInstanceService
from backend.services.spend_tracking_service import SpendTrackingService


@pytest.mark.asyncio
class TestPersonaInstanceLifecycleIntegration:
    """Integration tests with real database"""
    
    @pytest.fixture
    async def lifecycle_service(self, db):
        """Create lifecycle service with real database"""
        service = PersonaInstanceLifecycle(db)
        await service.initialize()
        yield service
        await service.close()
    
    @pytest.fixture
    async def test_persona_type(self, db):
        """Create a test persona type"""
        repo = PersonaTypeRepository(db)
        
        persona_type = await repo.create(PersonaTypeCreate(
            type_name=f"lifecycle-test-{uuid4().hex[:8]}",
            display_name="Lifecycle Test Developer",
            category=PersonaCategory.DEVELOPMENT,
            description="Test persona for lifecycle testing",
            base_workflow_id="wf0",
            capabilities=["coding", "testing"],
            default_llm_config={
                "providers": [{
                    "provider": "openai",
                    "model_name": "gpt-4",
                    "temperature": 0.7
                }]
            }
        ))
        
        yield persona_type
        
        # Cleanup
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            persona_type.id
        )
    
    @pytest.fixture
    async def test_instance(self, db, test_persona_type, azure_devops_config):
        """Create a test persona instance"""
        service = PersonaInstanceService(db)
        
        instance = await service.create_instance(PersonaInstanceCreate(
            instance_name=f"LifecycleTest-{uuid4().hex[:8]}",
            persona_type_id=test_persona_type.id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="LifecycleTestProject",
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("100.00"),
            spend_limit_monthly=Decimal("2000.00")
        ))
        
        yield instance
        
        # Cleanup
        await db.execute_query(
            "DELETE FROM orchestrator.persona_instances WHERE id = $1",
            instance.id
        )
    
    async def test_full_instance_lifecycle(self, lifecycle_service, test_instance):
        """Test complete instance lifecycle from provisioning to termination"""
        instance_id = test_instance.id
        
        # 1. Provision instance
        provision_event = await lifecycle_service.provision_instance(instance_id)
        assert provision_event.to_state == InstanceState.PROVISIONING
        
        # 2. Wait for initialization (background task)
        await asyncio.sleep(2)
        
        # 3. Check state after initialization
        state = await lifecycle_service.get_instance_state(instance_id)
        assert state in [InstanceState.ACTIVE, InstanceState.ERROR, InstanceState.INITIALIZING]
        
        # 4. If not active, manually transition for testing
        if state != InstanceState.ACTIVE:
            await lifecycle_service.transition_state(
                instance_id,
                InstanceState.ACTIVE,
                triggered_by="test"
            )
        
        # 5. Transition to busy
        busy_event = await lifecycle_service.transition_state(
            instance_id,
            InstanceState.BUSY,
            triggered_by="test",
            details={"task": "Processing test workload"}
        )
        assert busy_event.from_state == InstanceState.ACTIVE
        assert busy_event.to_state == InstanceState.BUSY
        
        # 6. Back to active
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.ACTIVE,
            triggered_by="test"
        )
        
        # 7. Pause instance
        pause_event = await lifecycle_service.pause_instance(
            instance_id,
            reason="Test pause",
            auto_resume_after=timedelta(seconds=5)
        )
        assert pause_event.to_state == InstanceState.PAUSED
        
        # 8. Resume instance
        resume_event = await lifecycle_service.resume_instance(instance_id)
        assert resume_event.to_state == InstanceState.ACTIVE
        
        # 9. Schedule maintenance
        maintenance_window = await lifecycle_service.schedule_maintenance(
            instance_id,
            datetime.utcnow() + timedelta(hours=1),
            timedelta(hours=2),
            "Test maintenance"
        )
        assert maintenance_window.instance_id == instance_id
        
        # 10. Terminate instance
        terminate_event = await lifecycle_service.terminate_instance(
            instance_id,
            reason="Test complete",
            force=True
        )
        assert terminate_event.to_state == InstanceState.TERMINATING
        
        # 11. Wait for cleanup
        await asyncio.sleep(6)
        
        # 12. Verify final state
        final_state = await lifecycle_service.get_instance_state(instance_id)
        assert final_state == InstanceState.TERMINATED
    
    async def test_lifecycle_event_persistence(self, lifecycle_service, test_instance):
        """Test that lifecycle events are properly persisted"""
        instance_id = test_instance.id
        
        # Create several state transitions
        await lifecycle_service.provision_instance(instance_id)
        await asyncio.sleep(1)
        
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.ACTIVE,
            triggered_by="test"
        )
        
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.BUSY,
            triggered_by="test"
        )
        
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.PAUSED,
            triggered_by="user",
            details={"reason": "User requested pause"}
        )
        
        # Retrieve history
        history = await lifecycle_service.get_lifecycle_history(
            instance_id,
            limit=10
        )
        
        # Verify events recorded
        assert len(history) >= 3
        
        # Check event details
        pause_events = [e for e in history if e.to_state == InstanceState.PAUSED]
        assert len(pause_events) > 0
        assert pause_events[0].triggered_by == "user"
        assert pause_events[0].details.get("reason") == "User requested pause"
    
    async def test_health_check_with_real_data(self, lifecycle_service, test_instance, db):
        """Test health check with real instance data"""
        instance_id = test_instance.id
        
        # Ensure instance is in lifecycle system
        await lifecycle_service.provision_instance(instance_id)
        await asyncio.sleep(1)
        
        # Add some spend data
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        await spend_service.record_llm_spend(
            instance_id,
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            ),
            input_tokens=1000,
            output_tokens=500,
            task_description="Test task"
        )
        
        # Perform health check
        health = await lifecycle_service.check_instance_health(instance_id)
        
        # Verify health check results
        assert health.status in [InstanceHealthStatus.HEALTHY, InstanceHealthStatus.WARNING]
        assert health.checks['instance_exists']
        assert health.checks['has_lifecycle_state']
        assert health.checks['llm_providers_healthy']
        
        # Check metrics populated
        assert 'current_state' in health.metrics
        assert 'daily_spend_percentage' in health.metrics
        assert 'monthly_spend_percentage' in health.metrics
        
        await spend_service.close()
    
    async def test_concurrent_state_transitions(self, lifecycle_service, test_instance):
        """Test handling concurrent state transition attempts"""
        instance_id = test_instance.id
        
        # Initialize instance
        await lifecycle_service.provision_instance(instance_id)
        await asyncio.sleep(1)
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.ACTIVE,
            triggered_by="test"
        )
        
        # Try concurrent transitions
        tasks = [
            lifecycle_service.transition_state(instance_id, InstanceState.BUSY, triggered_by="test1"),
            lifecycle_service.transition_state(instance_id, InstanceState.PAUSED, triggered_by="test2"),
            lifecycle_service.transition_state(instance_id, InstanceState.ERROR, triggered_by="test3")
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # At least one should succeed, others might fail with invalid transition
        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]
        
        assert len(successes) >= 1
        
        # Check final state is one of the attempted states
        final_state = await lifecycle_service.get_instance_state(instance_id)
        assert final_state in [InstanceState.BUSY, InstanceState.PAUSED, InstanceState.ERROR]
    
    async def test_auto_resume_functionality(self, lifecycle_service, test_instance):
        """Test automatic resume after pause"""
        instance_id = test_instance.id
        
        # Initialize and activate
        await lifecycle_service.provision_instance(instance_id)
        await asyncio.sleep(1)
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.ACTIVE,
            triggered_by="test"
        )
        
        # Pause with auto-resume
        await lifecycle_service.pause_instance(
            instance_id,
            reason="Short pause",
            auto_resume_after=timedelta(seconds=3)
        )
        
        # Verify paused
        state = await lifecycle_service.get_instance_state(instance_id)
        assert state == InstanceState.PAUSED
        
        # Wait for auto-resume
        await asyncio.sleep(4)
        
        # Verify resumed
        state = await lifecycle_service.get_instance_state(instance_id)
        assert state == InstanceState.ACTIVE
    
    async def test_monitoring_with_multiple_instances(self, lifecycle_service, db, test_persona_type, azure_devops_config):
        """Test monitoring functionality with multiple instances"""
        instances = []
        instance_service = PersonaInstanceService(db)
        
        # Create multiple instances
        for i in range(3):
            instance = await instance_service.create_instance(PersonaInstanceCreate(
                instance_name=f"MonitorTest-{i}-{uuid4().hex[:8]}",
                persona_type_id=test_persona_type.id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project="MonitorTestProject",
                llm_providers=[LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY"
                )],
                spend_limit_daily=Decimal("50.00"),
                spend_limit_monthly=Decimal("1000.00")
            ))
            instances.append(instance)
            
            # Initialize lifecycle
            await lifecycle_service.provision_instance(instance.id)
        
        await asyncio.sleep(2)
        
        # Set different states
        await lifecycle_service.transition_state(instances[0].id, InstanceState.ACTIVE, triggered_by="test")
        await lifecycle_service.transition_state(instances[1].id, InstanceState.ACTIVE, triggered_by="test")
        await lifecycle_service.transition_state(instances[1].id, InstanceState.BUSY, triggered_by="test")
        await lifecycle_service.transition_state(instances[2].id, InstanceState.ACTIVE, triggered_by="test")
        await lifecycle_service.transition_state(instances[2].id, InstanceState.PAUSED, triggered_by="test")
        
        # Monitor all
        results = await lifecycle_service.monitor_all_instances()
        
        # Verify monitoring results
        assert results['total_instances'] >= 3
        assert results['by_state'].get('active', 0) >= 1
        assert results['by_state'].get('busy', 0) >= 1
        assert results['by_state'].get('paused', 0) >= 1
        
        # Cleanup
        for instance in instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance.id
            )
    
    async def test_error_recovery_flow(self, lifecycle_service, test_instance):
        """Test error state recovery workflow"""
        instance_id = test_instance.id
        
        # Initialize
        await lifecycle_service.provision_instance(instance_id)
        await asyncio.sleep(1)
        
        # Force error state
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.ERROR,
            triggered_by="test",
            details={"error": "Simulated error for testing"}
        )
        
        # Verify error state
        state = await lifecycle_service.get_instance_state(instance_id)
        assert state == InstanceState.ERROR
        
        # Attempt recovery by re-initializing
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.INITIALIZING,
            triggered_by="system",
            details={"action": "error_recovery"}
        )
        
        # Transition back to active
        await lifecycle_service.transition_state(
            instance_id,
            InstanceState.ACTIVE,
            triggered_by="system",
            details={"recovery": "successful"}
        )
        
        # Verify recovery
        state = await lifecycle_service.get_instance_state(instance_id)
        assert state == InstanceState.ACTIVE
        
        # Check history shows recovery
        history = await lifecycle_service.get_lifecycle_history(instance_id)
        recovery_events = [e for e in history if e.details.get("recovery") == "successful"]
        assert len(recovery_events) > 0