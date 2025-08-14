"""
End-to-end tests for PersonaInstanceFactory
"""

import pytest
from uuid import uuid4
from decimal import Decimal
import asyncio

from backend.factories.persona_instance_factory import PersonaInstanceFactory
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.persona_instance_service import PersonaInstanceService


@pytest.mark.e2e
@pytest.mark.asyncio
class TestPersonaInstanceFactoryE2E:
    """End-to-end tests simulating real-world factory usage scenarios"""
    
    @pytest.mark.skip(reason="Standard team method requires specific persona type names")
    async def test_startup_creates_complete_development_team(self, db, azure_devops_config, clean_test_data):
        """Test creating a complete development team for a new startup project"""
        type_repo = PersonaTypeRepository(db)
        factory = PersonaInstanceFactory(db)
        service = PersonaInstanceService(db)
        
        # Create all required persona types for a startup
        print("\n=== Creating Persona Types for Startup Team ===")
        
        persona_types = {}
        startup_roles = [
            ("senior-developer", "Senior Developer", PersonaCategory.DEVELOPMENT,
             "Senior full-stack developer with architecture knowledge"),
            ("qa-engineer", "QA Engineer", PersonaCategory.TESTING,
             "Quality assurance and test automation"),
            ("product-owner", "Product Owner", PersonaCategory.MANAGEMENT,
             "Product management and stakeholder communication"),
            ("devsecops-engineer", "DevSecOps Engineer", PersonaCategory.OPERATIONS,
             "Cloud infrastructure and CI/CD")
        ]
        
        for type_name, display_name, category, description in startup_roles:
            unique_name = f"{type_name}-{uuid4().hex[:8]}"
            persona_type = await type_repo.create(PersonaTypeCreate(
                type_name=unique_name,
                display_name=display_name,
                category=category,
                description=description,
                base_workflow_id="wf0-feature-development"
            ))
            persona_types[type_name] = persona_type
            print(f"Created persona type: {display_name} ({unique_name})")
        
        # Use factory to create a small startup team
        print("\n=== Creating Startup Team Instances ===")
        
        team = await factory.create_standard_development_team(
            project_name="Startup MVP",
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=azure_devops_config["test_project"],
            team_size="small"
        )
        
        print(f"Created {len(team)} team members")
        
        # Simulate first sprint of work
        print("\n=== Simulating First Sprint ===")
        
        sprint_tasks = [
            ("lead_developer", [
                ("Setup project architecture", Decimal("12.50")),
                ("Implement authentication system", Decimal("18.75")),
                ("Create core API endpoints", Decimal("15.00")),
                ("Code review and mentoring", Decimal("8.50"))
            ]),
            ("qa_engineer", [
                ("Setup test framework", Decimal("6.25")),
                ("Write initial test suite", Decimal("10.00")),
                ("Create CI/CD test pipeline", Decimal("7.50")),
                ("Manual testing of MVP features", Decimal("5.00"))
            ])
        ]
        
        total_spend = Decimal("0.00")
        
        for role, tasks in sprint_tasks:
            if role in team:
                instance = team[role]
                print(f"\n{role.replace('_', ' ').title()} working on:")
                
                for task_name, cost in tasks:
                    await service.record_spend(instance.id, cost, task_name)
                    total_spend += cost
                    print(f"  - {task_name}: ${cost}")
                    await asyncio.sleep(0.1)  # Simulate time between tasks
                
                # Check instance status
                updated = await service.get_instance(instance.id)
                print(f"  Daily spend: ${updated.current_spend_daily} ({updated.spend_percentage_daily:.1f}% of limit)")
        
        print(f"\nTotal sprint spend: ${total_spend}")
        
        # Get team performance metrics
        stats = await service.get_instance_statistics()
        print("\n=== Team Statistics ===")
        print(f"Active instances: {stats['active_instances']}")
        print(f"Total daily spend: ${stats['total_daily_spend']}")
        print(f"Projects covered: {len(stats['by_project'])}")
        
        # Verify team is within budget
        for role, instance in team.items():
            current = await service.get_instance(instance.id)
            assert current.current_spend_daily <= current.spend_limit_daily
            print(f"{role}: Within daily budget ✓")
        
        # Clean up (keeping only the types we created)
        print("\n=== Cleanup ===")
        created_instance_ids = [inst.id for inst in team.values()]
        for instance_id in created_instance_ids:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
        
        for persona_type in persona_types.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_type.id
            )
        
        print("Cleanup complete")
    
    @pytest.mark.skip(reason="Standard team method requires specific persona type names")
    async def test_enterprise_team_scaling(self, db, azure_devops_config, clean_test_data):
        """Test scaling from small to large enterprise team"""
        type_repo = PersonaTypeRepository(db)
        factory = PersonaInstanceFactory(db)
        service = PersonaInstanceService(db)
        
        print("\n=== Enterprise Team Scaling Scenario ===")
        
        # Create all required persona types
        required_types = [
            # Core team (small/medium)
            ("senior-developer", "Senior Developer", PersonaCategory.DEVELOPMENT),
            ("qa-engineer", "QA Engineer", PersonaCategory.TESTING),
            # Medium team additions
            ("software-architect", "Software Architect", PersonaCategory.ARCHITECTURE),
            ("backend-developer", "Backend Developer", PersonaCategory.DEVELOPMENT),
            ("frontend-developer", "Frontend Developer", PersonaCategory.DEVELOPMENT),
            ("devsecops-engineer", "DevSecOps Engineer", PersonaCategory.OPERATIONS),
            # Large team additions
            ("product-owner", "Product Owner", PersonaCategory.MANAGEMENT),
            ("technical-writer", "Technical Writer", PersonaCategory.SPECIALIZED)
        ]
        
        persona_types = {}
        for type_name, display_name, category in required_types:
            unique_name = f"{type_name}-{uuid4().hex[:8]}"
            persona_type = await type_repo.create(PersonaTypeCreate(
                type_name=unique_name,
                display_name=display_name,
                category=category,
                description=f"{display_name} for enterprise project",
                base_workflow_id="wf0-feature-development"
            ))
            persona_types[type_name] = persona_type
        
        # Phase 1: Start with small team
        print("\nPhase 1: Small Team (Proof of Concept)")
        small_team = await factory.create_standard_development_team(
            project_name="Enterprise App v1",
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=azure_devops_config["test_project"],
            team_size="small"
        )
        print(f"Small team size: {len(small_team)} members")
        
        # Simulate POC development
        for role, instance in small_team.items():
            await service.record_spend(
                instance.id,
                Decimal("10.00"),
                "POC development"
            )
        
        # Phase 2: Scale to medium team
        print("\nPhase 2: Medium Team (MVP Development)")
        
        # Deactivate small team instances
        for instance in small_team.values():
            await service.deactivate_instance(instance.id)
        
        medium_team = await factory.create_standard_development_team(
            project_name="Enterprise App v2",
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=azure_devops_config["test_project"],
            team_size="medium"
        )
        print(f"Medium team size: {len(medium_team)} members")
        
        # Simulate MVP development with parallel work
        tasks = []
        for role, instance in medium_team.items():
            task = service.record_spend(
                instance.id,
                Decimal("15.00"),
                f"MVP feature - {role}"
            )
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Phase 3: Scale to large team
        print("\nPhase 3: Large Team (Production Release)")
        
        # Deactivate medium team
        for instance in medium_team.values():
            await service.deactivate_instance(instance.id)
        
        large_team = await factory.create_standard_development_team(
            project_name="Enterprise App v3",
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=azure_devops_config["test_project"],
            team_size="large"
        )
        print(f"Large team size: {len(large_team)} members")
        
        # Verify team composition and priorities
        print("\nTeam Structure:")
        for role, instance in sorted(large_team.items(), key=lambda x: x[1].priority_level, reverse=True):
            print(f"  {role}: Priority {instance.priority_level}, "
                  f"Max tasks: {instance.max_concurrent_tasks}")
        
        # Simulate production workload
        production_tasks = {
            "chief_architect": Decimal("25.00"),
            "backend_team_lead": Decimal("35.00"),
            "frontend_team_lead": Decimal("35.00"),
            "qa_manager": Decimal("30.00"),
            "devops_lead": Decimal("40.00"),
            "product_owner": Decimal("20.00"),
            "technical_writer": Decimal("15.00")
        }
        
        for role, spend in production_tasks.items():
            if role in large_team:
                await service.record_spend(
                    large_team[role].id,
                    spend,
                    "Production release preparation"
                )
        
        # Get final statistics
        stats = await service.get_instance_statistics()
        print(f"\nTotal instances created: {len(small_team) + len(medium_team) + len(large_team)}")
        print(f"Currently active: {stats['active_instances']}")
        print(f"Total daily spend: ${stats['total_daily_spend']}")
        
        # Clean up all instances
        all_instances = list(small_team.values()) + list(medium_team.values()) + list(large_team.values())
        for instance in all_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance.id
            )
        
        for persona_type in persona_types.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_type.id
            )
    
    async def test_multi_project_persona_deployment(self, db, azure_devops_config, clean_test_data):
        """Test deploying personas across multiple projects"""
        type_repo = PersonaTypeRepository(db)
        factory = PersonaInstanceFactory(db)
        service = PersonaInstanceService(db)
        
        print("\n=== Multi-Project Deployment Scenario ===")
        
        # Create a versatile architect persona type
        architect_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"enterprise-architect-{uuid4().hex[:8]}",
            display_name="Enterprise Architect",
            category=PersonaCategory.ARCHITECTURE,
            description="Cross-project architecture oversight",
            base_workflow_id="wf0-feature-development",
            default_capabilities={
                "cross_project_visibility": True,
                "architecture_governance": True,
                "technology_standardization": True
            }
        ))
        
        # Create architect instance for first project
        print("\nDeploying architect to multiple projects:")
        
        projects = [
            ("Customer Portal", "customer-portal", {"focus": "user_experience"}),
            ("Admin Dashboard", "admin-dashboard", {"focus": "data_analytics"}),
            ("Mobile App", "mobile-app", {"focus": "performance"})
        ]
        
        architect_instances = []
        
        for project_name, repo_name, settings in projects:
            instance = await factory.create_instance(
                instance_name=f"TEST_Enterprise_Architect_{project_name}_{uuid4().hex[:8]}",
                persona_type_id=architect_type.id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=azure_devops_config["test_project"],
                repository_name=repo_name,
                custom_settings=settings,
                max_concurrent_tasks=3,  # Limited capacity per project
                priority_level=10  # High priority
            )
            architect_instances.append(instance)
            print(f"  ✓ Deployed to {project_name}")
        
        # Simulate cross-project work
        print("\nSimulating cross-project activities:")
        
        activities = [
            ("Standardize API design", Decimal("8.50")),
            ("Security architecture review", Decimal("12.00")),
            ("Performance optimization strategy", Decimal("10.00"))
        ]
        
        for activity, cost in activities:
            print(f"\n{activity}:")
            for i, instance in enumerate(architect_instances):
                # Each project gets a portion of the architect's time
                project_cost = cost / len(architect_instances)
                await service.record_spend(instance.id, project_cost, activity)
                print(f"  Project {i+1}: ${project_cost}")
        
        # Check utilization across projects
        print("\nArchitect utilization by project:")
        for i, instance in enumerate(architect_instances):
            current = await service.get_instance(instance.id)
            print(f"  Project {i+1}: ${current.current_spend_daily} "
                  f"({current.spend_percentage_daily:.1f}% of limit)")
        
        # Clean up
        for instance in architect_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance.id
            )
        
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            architect_type.id
        )
        
        print("\nMulti-project deployment complete")