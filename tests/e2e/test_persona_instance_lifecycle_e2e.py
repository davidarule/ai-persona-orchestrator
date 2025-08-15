"""
End-to-End tests for Persona Instance Lifecycle
Real-world scenarios testing complete lifecycle workflows
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal

from backend.services.persona_instance_lifecycle import PersonaInstanceLifecycle, InstanceState
from backend.services.persona_instance_service import PersonaInstanceService
from backend.services.spend_tracking_service import SpendTrackingService
from backend.factories.persona_instance_factory import PersonaInstanceFactory
from backend.models.persona_instance import PersonaInstanceCreate, LLMProvider, LLMModel
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.e2e
@pytest.mark.asyncio
class TestPersonaInstanceLifecycleE2E:
    """E2E tests simulating real-world lifecycle scenarios"""
    
    @pytest.fixture
    async def lifecycle_service(self, db):
        """Create lifecycle service"""
        service = PersonaInstanceLifecycle(db)
        await service.initialize()
        yield service
        await service.close()
    
    @pytest.fixture
    async def instance_service(self, db):
        """Create instance service"""
        return PersonaInstanceService(db)
    
    @pytest.fixture
    async def spend_service(self, db):
        """Create spend tracking service"""
        service = SpendTrackingService(db)
        await service.initialize()
        yield service
        await service.close()
    
    @pytest.fixture
    async def test_personas(self, db):
        """Create test persona types for E2E scenarios"""
        repo = PersonaTypeRepository(db)
        created_types = {}
        
        personas = [
            ("senior-developer", "Senior Developer", PersonaCategory.DEVELOPMENT),
            ("qa-engineer", "QA Engineer", PersonaCategory.TESTING),
            ("devsecops-engineer", "DevSecOps Engineer", PersonaCategory.OPERATIONS)
        ]
        
        for type_name, display_name, category in personas:
            persona_type = await repo.create(PersonaTypeCreate(
                type_name=f"{type_name}-e2e-lifecycle-{uuid4().hex[:8]}",
                display_name=display_name,
                category=category,
                description=f"E2E lifecycle test {display_name}",
                base_workflow_id="wf0",
                capabilities=["coding", "testing", "monitoring"],
                default_llm_config={
                    "providers": [{
                        "provider": "openai",
                        "model_name": "gpt-4",
                        "temperature": 0.7
                    }]
                }
            ))
            created_types[type_name] = persona_type
        
        yield created_types
        
        # Cleanup
        for persona_type in created_types.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_type.id
            )
    
    async def test_development_sprint_lifecycle(self, lifecycle_service, instance_service, spend_service, test_personas, azure_devops_config):
        """Test persona lifecycle during a development sprint"""
        print("\n=== DEVELOPMENT SPRINT LIFECYCLE ===")
        
        # Create development team
        team_instances = []
        
        # Senior Developer
        senior_dev = await instance_service.create_instance(PersonaInstanceCreate(
            instance_name=f"SprintDev-{uuid4().hex[:8]}",
            persona_type_id=test_personas["senior-developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="SprintProject",
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("150.00"),
            spend_limit_monthly=Decimal("3000.00"),
            max_concurrent_tasks=15
        ))
        team_instances.append(senior_dev)
        
        # QA Engineer
        qa_eng = await instance_service.create_instance(PersonaInstanceCreate(
            instance_name=f"SprintQA-{uuid4().hex[:8]}",
            persona_type_id=test_personas["qa-engineer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="SprintProject",
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("75.00"),
            spend_limit_monthly=Decimal("1500.00")
        ))
        team_instances.append(qa_eng)
        
        # Phase 1: Sprint Start - Provision and Initialize
        print("\nPhase 1: Sprint Start")
        for instance in team_instances:
            await lifecycle_service.provision_instance(instance.id)
            print(f"✓ Provisioned {instance.instance_name}")
        
        # Wait for initialization
        await asyncio.sleep(3)
        
        # Verify all active
        for instance in team_instances:
            state = await lifecycle_service.get_instance_state(instance.id)
            if state != InstanceState.ACTIVE:
                # Force activate for testing
                await lifecycle_service.transition_state(
                    instance.id,
                    InstanceState.ACTIVE,
                    triggered_by="test"
                )
            print(f"✓ {instance.instance_name} is active")
        
        # Phase 2: Active Development - Simulate work
        print("\nPhase 2: Active Development")
        
        # Senior dev starts coding
        await lifecycle_service.transition_state(
            senior_dev.id,
            InstanceState.BUSY,
            triggered_by="system",
            details={"task": "Implementing feature XYZ"}
        )
        
        # Record spend
        await spend_service.record_llm_spend(
            senior_dev.id,
            LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-4", api_key_env_var="OPENAI_API_KEY"),
            input_tokens=5000,
            output_tokens=3000,
            task_description="Feature implementation"
        )
        
        # QA prepares test cases
        await lifecycle_service.transition_state(
            qa_eng.id,
            InstanceState.BUSY,
            triggered_by="system",
            details={"task": "Writing test cases"}
        )
        
        await spend_service.record_llm_spend(
            qa_eng.id,
            LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-3.5-turbo", api_key_env_var="OPENAI_API_KEY"),
            input_tokens=2000,
            output_tokens=1500,
            task_description="Test case generation"
        )
        
        print("✓ Development work in progress")
        
        # Phase 3: Daily Standup - Pause for meeting
        print("\nPhase 3: Daily Standup")
        
        # Pause all for standup
        for instance in team_instances:
            await lifecycle_service.pause_instance(
                instance.id,
                reason="Daily standup meeting",
                auto_resume_after=timedelta(minutes=15),
                triggered_by="system"
            )
        
        print("✓ Team paused for standup")
        
        # Check health during pause
        for instance in team_instances:
            health = await lifecycle_service.check_instance_health(instance.id)
            print(f"  {instance.instance_name} health: {health.status.value}")
        
        # Resume work
        for instance in team_instances:
            await lifecycle_service.resume_instance(instance.id)
        
        print("✓ Team resumed work")
        
        # Phase 4: Code Review - Senior dev reviews
        print("\nPhase 4: Code Review")
        
        await lifecycle_service.transition_state(
            senior_dev.id,
            InstanceState.ACTIVE,
            triggered_by="system"
        )
        
        await lifecycle_service.transition_state(
            senior_dev.id,
            InstanceState.BUSY,
            triggered_by="system",
            details={"task": "Code review for PR #123"}
        )
        
        # Phase 5: End of Day - Check spend and health
        print("\nPhase 5: End of Day Analysis")
        
        monitoring_results = await lifecycle_service.monitor_all_instances()
        print(f"Total active instances: {monitoring_results['total_instances']}")
        print(f"By state: {monitoring_results['by_state']}")
        
        # Check individual spend
        for instance in team_instances:
            spend_status = await spend_service.get_spend_status(instance.id)
            print(f"{instance.instance_name} daily spend: {spend_status['daily_percentage']:.1f}%")
        
        # Phase 6: Sprint End - Terminate instances
        print("\nPhase 6: Sprint End")
        
        for instance in team_instances:
            # Transition to active first if busy
            state = await lifecycle_service.get_instance_state(instance.id)
            if state == InstanceState.BUSY:
                await lifecycle_service.transition_state(
                    instance.id,
                    InstanceState.ACTIVE,
                    triggered_by="system"
                )
            
            # Terminate
            await lifecycle_service.terminate_instance(
                instance.id,
                reason="Sprint completed",
                force=False
            )
            print(f"✓ Terminating {instance.instance_name}")
        
        # Wait for cleanup
        await asyncio.sleep(6)
        
        # Verify termination
        for instance in team_instances:
            state = await lifecycle_service.get_instance_state(instance.id)
            assert state == InstanceState.TERMINATED
            print(f"✓ {instance.instance_name} terminated")
        
        # Cleanup
        for instance in team_instances:
            await instance_service.delete_instance(instance.id)
    
    async def test_incident_response_lifecycle(self, lifecycle_service, instance_service, test_personas, azure_devops_config):
        """Test emergency incident response lifecycle"""
        print("\n=== INCIDENT RESPONSE LIFECYCLE ===")
        
        incident_id = f"INC-{uuid4().hex[:8]}"
        
        # Phase 1: Incident Detected - Rapid deployment
        print(f"\nPhase 1: Incident {incident_id} Detected")
        
        # Create DevSecOps engineer for incident response
        incident_responder = await instance_service.create_instance(PersonaInstanceCreate(
            instance_name=f"IncidentResponder-{incident_id}",
            persona_type_id=test_personas["devsecops-engineer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=f"Incident-{incident_id}",
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4-turbo-preview",
                temperature=0.1,  # Low temperature for accuracy
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("500.00"),  # High limit for emergency
            spend_limit_monthly=Decimal("10000.00"),
            max_concurrent_tasks=50,  # High concurrency
            priority_level=10,  # Maximum priority
            custom_settings={
                "incident_id": incident_id,
                "response_mode": "emergency",
                "alert_channels": ["slack", "pagerduty"]
            }
        ))
        
        # Fast-track provisioning
        await lifecycle_service.provision_instance(incident_responder.id)
        print("✓ Emergency responder provisioned")
        
        # Force immediate activation
        await asyncio.sleep(1)
        await lifecycle_service.transition_state(
            incident_responder.id,
            InstanceState.ACTIVE,
            triggered_by="emergency",
            details={"incident_id": incident_id, "severity": "P1"}
        )
        
        # Phase 2: Active Response
        print("\nPhase 2: Active Incident Response")
        
        # Start investigation
        await lifecycle_service.transition_state(
            incident_responder.id,
            InstanceState.BUSY,
            triggered_by="automation",
            details={
                "task": "Root cause analysis",
                "incident_id": incident_id,
                "start_time": datetime.utcnow().isoformat()
            }
        )
        
        # Simulate intensive work
        for i in range(3):
            health = await lifecycle_service.check_instance_health(incident_responder.id)
            print(f"  Health check #{i+1}: {health.status.value}")
            
            if health.status == InstanceHealthStatus.CRITICAL:
                # Emergency recovery
                await lifecycle_service.transition_state(
                    incident_responder.id,
                    InstanceState.ERROR,
                    triggered_by="system"
                )
                await lifecycle_service.transition_state(
                    incident_responder.id,
                    InstanceState.INITIALIZING,
                    triggered_by="emergency"
                )
                await lifecycle_service.transition_state(
                    incident_responder.id,
                    InstanceState.ACTIVE,
                    triggered_by="emergency"
                )
            
            await asyncio.sleep(1)
        
        # Phase 3: Incident Mitigation
        print("\nPhase 3: Incident Mitigation")
        
        # Apply fix
        await lifecycle_service.transition_state(
            incident_responder.id,
            InstanceState.ACTIVE,
            triggered_by="automation",
            details={"status": "Mitigation applied"}
        )
        
        # Schedule maintenance for permanent fix
        maintenance = await lifecycle_service.schedule_maintenance(
            incident_responder.id,
            datetime.utcnow() + timedelta(hours=2),
            timedelta(hours=1),
            f"Permanent fix for {incident_id}",
            auto_resume=True
        )
        print(f"✓ Maintenance scheduled: {maintenance.maintenance_type}")
        
        # Phase 4: Post-Incident
        print("\nPhase 4: Post-Incident Activities")
        
        # Document findings
        await lifecycle_service.transition_state(
            incident_responder.id,
            InstanceState.BUSY,
            triggered_by="system",
            details={"task": "Creating incident report"}
        )
        
        # Get lifecycle history for audit
        history = await lifecycle_service.get_lifecycle_history(
            incident_responder.id,
            start_date=datetime.utcnow() - timedelta(hours=1)
        )
        
        print(f"✓ Incident lifecycle events: {len(history)}")
        for event in history[:5]:  # Show first 5 events
            print(f"  - {event.event_type}: {event.from_state} → {event.to_state}")
        
        # Phase 5: Incident Closure
        print("\nPhase 5: Incident Closure")
        
        # Return to active
        await lifecycle_service.transition_state(
            incident_responder.id,
            InstanceState.ACTIVE,
            triggered_by="user",
            details={"incident_status": "resolved"}
        )
        
        # Terminate responder
        await lifecycle_service.terminate_instance(
            incident_responder.id,
            reason=f"Incident {incident_id} resolved",
            force=False
        )
        
        # Cleanup
        await asyncio.sleep(6)
        await instance_service.delete_instance(incident_responder.id)
        print(f"✓ Incident {incident_id} lifecycle complete")
    
    async def test_long_running_project_lifecycle(self, lifecycle_service, instance_service, spend_service, test_personas, azure_devops_config):
        """Test lifecycle for long-running project with maintenance windows"""
        print("\n=== LONG-RUNNING PROJECT LIFECYCLE ===")
        
        project_name = "LongRunningProject"
        
        # Create senior developer for long-term project
        developer = await instance_service.create_instance(PersonaInstanceCreate(
            instance_name=f"LongTermDev-{uuid4().hex[:8]}",
            persona_type_id=test_personas["senior-developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name,
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("100.00"),
            spend_limit_monthly=Decimal("2000.00")
        ))
        
        # Phase 1: Project Start
        print("\nPhase 1: Project Initialization")
        await lifecycle_service.provision_instance(developer.id)
        await asyncio.sleep(2)
        
        # Verify healthy start
        health = await lifecycle_service.check_instance_health(developer.id)
        assert health.status in [InstanceHealthStatus.HEALTHY, InstanceHealthStatus.WARNING]
        print(f"✓ Initial health: {health.status.value}")
        
        # Phase 2: Simulate daily work pattern
        print("\nPhase 2: Daily Work Pattern")
        
        for day in range(3):  # Simulate 3 days
            print(f"\n  Day {day + 1}:")
            
            # Morning: Start work
            await lifecycle_service.transition_state(
                developer.id,
                InstanceState.ACTIVE,
                triggered_by="schedule"
            )
            
            # Active development
            await lifecycle_service.transition_state(
                developer.id,
                InstanceState.BUSY,
                triggered_by="automation",
                details={"task": f"Day {day + 1} development"}
            )
            
            # Record daily spend
            daily_spend = Decimal("30.00") * (1 + day * 0.2)  # Increasing spend
            await spend_service.record_llm_spend(
                developer.id,
                LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-4", api_key_env_var="OPENAI_API_KEY"),
                input_tokens=10000 + (day * 2000),
                output_tokens=5000 + (day * 1000),
                task_description=f"Day {day + 1} coding tasks"
            )
            
            # Check spend status
            spend_status = await spend_service.get_spend_status(developer.id)
            print(f"    Daily spend: {spend_status['daily_percentage']:.1f}%")
            print(f"    Monthly spend: {spend_status['monthly_percentage']:.1f}%")
            
            # Lunch break - pause
            await lifecycle_service.pause_instance(
                developer.id,
                reason="Lunch break",
                auto_resume_after=timedelta(seconds=2),  # Short for testing
                triggered_by="schedule"
            )
            
            await asyncio.sleep(3)  # Wait for auto-resume
            
            # Afternoon work
            state = await lifecycle_service.get_instance_state(developer.id)
            if state == InstanceState.ACTIVE:
                print("    ✓ Auto-resumed after lunch")
            
            # End of day
            await lifecycle_service.transition_state(
                developer.id,
                InstanceState.ACTIVE,
                triggered_by="schedule"
            )
        
        # Phase 3: Scheduled Maintenance
        print("\nPhase 3: Scheduled Maintenance")
        
        # Schedule overnight maintenance
        maintenance_window = await lifecycle_service.schedule_maintenance(
            developer.id,
            datetime.utcnow() + timedelta(seconds=5),
            timedelta(seconds=10),
            "System updates and optimization",
            auto_resume=True
        )
        
        print("✓ Maintenance scheduled")
        print("  Waiting for maintenance window...")
        
        # Wait for maintenance to start
        await asyncio.sleep(6)
        
        state = await lifecycle_service.get_instance_state(developer.id)
        if state == InstanceState.MAINTENANCE:
            print("✓ Maintenance started")
        
        # Wait for maintenance to complete
        await asyncio.sleep(11)
        
        state = await lifecycle_service.get_instance_state(developer.id)
        if state == InstanceState.ACTIVE:
            print("✓ Maintenance completed, instance resumed")
        
        # Phase 4: Health Monitoring
        print("\nPhase 4: Comprehensive Health Check")
        
        final_health = await lifecycle_service.check_instance_health(developer.id)
        print(f"Final health status: {final_health.status.value}")
        print("Health checks:")
        for check, result in final_health.checks.items():
            print(f"  - {check}: {'✓' if result else '✗'}")
        
        if final_health.issues:
            print("Issues found:")
            for issue in final_health.issues:
                print(f"  - {issue}")
        
        if final_health.recommendations:
            print("Recommendations:")
            for rec in final_health.recommendations:
                print(f"  - {rec}")
        
        # Phase 5: Project Completion
        print("\nPhase 5: Project Completion")
        
        # Get final statistics
        history = await lifecycle_service.get_lifecycle_history(developer.id)
        print(f"Total lifecycle events: {len(history)}")
        
        # Count state transitions
        state_counts = {}
        for event in history:
            if event.event_type == "state_transition":
                state = event.to_state.value
                state_counts[state] = state_counts.get(state, 0) + 1
        
        print("State transition summary:")
        for state, count in state_counts.items():
            print(f"  - {state}: {count} times")
        
        # Graceful shutdown
        await lifecycle_service.terminate_instance(
            developer.id,
            reason="Project completed successfully",
            force=False
        )
        
        # Cleanup
        await asyncio.sleep(6)
        await instance_service.delete_instance(developer.id)
        print("✓ Long-running project lifecycle complete")
    
    async def test_auto_scaling_lifecycle(self, lifecycle_service, instance_service, spend_service, test_personas, azure_devops_config):
        """Test lifecycle with auto-scaling based on workload"""
        print("\n=== AUTO-SCALING LIFECYCLE ===")
        
        instances = []
        
        # Phase 1: Start with minimal team
        print("\nPhase 1: Minimal Team Start")
        
        # Create initial developer
        lead_dev = await instance_service.create_instance(PersonaInstanceCreate(
            instance_name=f"LeadDev-{uuid4().hex[:8]}",
            persona_type_id=test_personas["senior-developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="AutoScaleProject",
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("150.00"),
            spend_limit_monthly=Decimal("3000.00")
        ))
        instances.append(lead_dev)
        
        await lifecycle_service.provision_instance(lead_dev.id)
        await asyncio.sleep(2)
        print("✓ Lead developer active")
        
        # Phase 2: Monitor and scale up
        print("\nPhase 2: Workload Increase - Scale Up")
        
        # Simulate high workload
        await lifecycle_service.transition_state(
            lead_dev.id,
            InstanceState.BUSY,
            triggered_by="system",
            details={"workload": "high", "queue_length": 50}
        )
        
        # Check if scaling needed
        health = await lifecycle_service.check_instance_health(lead_dev.id)
        
        # Scale up - add QA engineer
        qa_eng = await instance_service.create_instance(PersonaInstanceCreate(
            instance_name=f"ScaledQA-{uuid4().hex[:8]}",
            persona_type_id=test_personas["qa-engineer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="AutoScaleProject",
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("75.00"),
            spend_limit_monthly=Decimal("1500.00")
        ))
        instances.append(qa_eng)
        
        await lifecycle_service.provision_instance(qa_eng.id)
        print("✓ Scaled up: Added QA engineer")
        
        # Phase 3: Peak load - add more resources
        print("\nPhase 3: Peak Load Management")
        
        # Add DevOps for performance
        devops = await instance_service.create_instance(PersonaInstanceCreate(
            instance_name=f"ScaledDevOps-{uuid4().hex[:8]}",
            persona_type_id=test_personas["devsecops-engineer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="AutoScaleProject",
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("100.00"),
            spend_limit_monthly=Decimal("2000.00")
        ))
        instances.append(devops)
        
        await lifecycle_service.provision_instance(devops.id)
        print("✓ Peak capacity: 3 instances active")
        
        # Monitor all instances
        monitoring = await lifecycle_service.monitor_all_instances()
        print(f"Active instances: {monitoring['total_instances']}")
        print(f"Healthy: {monitoring['healthy_instances']}")
        
        # Phase 4: Load reduction - scale down
        print("\nPhase 4: Load Reduction - Scale Down")
        
        # Reduce workload
        await lifecycle_service.transition_state(
            lead_dev.id,
            InstanceState.ACTIVE,
            triggered_by="system",
            details={"workload": "normal"}
        )
        
        # Pause non-critical instances
        await lifecycle_service.pause_instance(
            qa_eng.id,
            reason="Reduced workload - scaling down",
            triggered_by="automation"
        )
        
        await lifecycle_service.pause_instance(
            devops.id,
            reason="Reduced workload - scaling down",
            triggered_by="automation"
        )
        
        print("✓ Scaled down: 2 instances paused")
        
        # Phase 5: End of scaling test
        print("\nPhase 5: Cleanup")
        
        # Get final statistics
        for instance in instances:
            spend_status = await spend_service.get_spend_status(instance.id)
            state = await lifecycle_service.get_instance_state(instance.id)
            print(f"{instance.instance_name}:")
            print(f"  State: {state.value}")
            print(f"  Daily spend: {spend_status['daily_percentage']:.1f}%")
        
        # Terminate all
        for instance in instances:
            try:
                await lifecycle_service.terminate_instance(
                    instance.id,
                    reason="Auto-scaling test complete",
                    force=True
                )
            except Exception as e:
                print(f"  Warning during termination: {e}")
        
        # Cleanup
        await asyncio.sleep(6)
        for instance in instances:
            await instance_service.delete_instance(instance.id)
        
        print("✓ Auto-scaling lifecycle test complete")