"""
Integration tests for PersonaInstanceFactory
"""

import pytest
from uuid import uuid4
from decimal import Decimal

from backend.factories.persona_instance_factory import PersonaInstanceFactory
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.persona_instance_service import PersonaInstanceService


@pytest.mark.integration
@pytest.mark.asyncio
class TestPersonaInstanceFactoryIntegration:
    """Integration tests for PersonaInstanceFactory with real database"""
    
    async def test_complete_team_creation_workflow(self, db, azure_devops_config, clean_test_data):
        """Test creating a complete team for a real project"""
        type_repo = PersonaTypeRepository(db)
        factory = PersonaInstanceFactory(db)
        service = PersonaInstanceService(db)
        
        # Create all required persona types
        persona_types = {
            "software-architect": await type_repo.create(PersonaTypeCreate(
                type_name=f"software-architect-{uuid4().hex[:8]}",
                display_name="Software Architect",
                category=PersonaCategory.ARCHITECTURE,
                description="System architecture and design",
                base_workflow_id="wf0-feature-development",
                default_capabilities={
                    "system_design": True,
                    "code_review": True,
                    "technical_documentation": True
                }
            )),
            "backend-developer": await type_repo.create(PersonaTypeCreate(
                type_name=f"backend-developer-{uuid4().hex[:8]}",
                display_name="Backend Developer",
                category=PersonaCategory.DEVELOPMENT,
                description="Backend API development",
                base_workflow_id="wf0-feature-development"
            )),
            "frontend-developer": await type_repo.create(PersonaTypeCreate(
                type_name=f"frontend-developer-{uuid4().hex[:8]}",
                display_name="Frontend Developer",
                category=PersonaCategory.DEVELOPMENT,
                description="Frontend UI development",
                base_workflow_id="wf0-feature-development"
            )),
            "qa-engineer": await type_repo.create(PersonaTypeCreate(
                type_name=f"qa-engineer-{uuid4().hex[:8]}",
                display_name="QA Engineer",
                category=PersonaCategory.TESTING,
                description="Quality assurance and testing",
                base_workflow_id="wf9-monitoring"
            )),
            "devsecops-engineer": await type_repo.create(PersonaTypeCreate(
                type_name=f"devsecops-engineer-{uuid4().hex[:8]}",
                display_name="DevSecOps Engineer",
                category=PersonaCategory.OPERATIONS,
                description="DevOps and security operations",
                base_workflow_id="wf16-deploy-application"
            )),
            "product-owner": await type_repo.create(PersonaTypeCreate(
                type_name=f"product-owner-{uuid4().hex[:8]}",
                display_name="Product Owner",
                category=PersonaCategory.MANAGEMENT,
                description="Product management and planning",
                base_workflow_id="wf12-repository-setup"
            ))
        }
        
        # Create team configuration
        team_config = {
            "chief_architect": {
                "persona_type_name": persona_types["software-architect"].type_name,
                "repository": "architecture-docs",
                "priority": 10,
                "settings": {
                    "focus_areas": ["microservices", "event-driven", "cloud-native"],
                    "documentation_standard": "ADR"
                }
            },
            "backend_lead": {
                "persona_type_name": persona_types["backend-developer"].type_name,
                "repository": "backend-api",
                "priority": 8,
                "max_tasks": 10,
                "settings": {
                    "api_style": "RESTful",
                    "database_preference": "PostgreSQL"
                }
            },
            "frontend_lead": {
                "persona_type_name": persona_types["frontend-developer"].type_name,
                "repository": "frontend-app",
                "priority": 8,
                "max_tasks": 10,
                "settings": {
                    "framework": "React",
                    "state_management": "Redux"
                }
            },
            "qa_manager": {
                "persona_type_name": persona_types["qa-engineer"].type_name,
                "repository": "test-automation",
                "priority": 7,
                "settings": {
                    "test_framework": "pytest",
                    "coverage_target": 85
                }
            },
            "devops_lead": {
                "persona_type_name": persona_types["devsecops-engineer"].type_name,
                "repository": "infrastructure",
                "priority": 7,
                "settings": {
                    "ci_cd": "GitHub Actions",
                    "cloud_provider": "Azure"
                }
            },
            "product_owner": {
                "persona_type_name": persona_types["product-owner"].type_name,
                "priority": 9,
                "max_tasks": 5,
                "settings": {
                    "methodology": "Agile",
                    "sprint_length": "2 weeks"
                }
            }
        }
        
        # Create the team
        team = await factory.create_team_instances(
            project_name="AI Orchestrator Integration",
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=azure_devops_config["test_project"],
            team_config=team_config
        )
        
        # Verify team creation
        assert len(team) == 6
        
        # Verify each team member
        for role, instance in team.items():
            assert instance is not None
            assert instance.azure_devops_org == azure_devops_config["org_url"]
            assert instance.azure_devops_project == azure_devops_config["test_project"]
            assert instance.is_active is True
            
            # Verify role-specific attributes
            if role == "chief_architect":
                assert instance.priority_level == 10
                assert "focus_areas" in instance.custom_settings
                assert instance.repository_name == "architecture-docs"
            elif role == "backend_lead":
                assert instance.max_concurrent_tasks == 10
                assert instance.custom_settings["api_style"] == "RESTful"
        
        # Test team collaboration - simulate work distribution
        work_items = [
            ("Design microservice architecture", "chief_architect"),
            ("Implement user API", "backend_lead"),
            ("Create dashboard UI", "frontend_lead"),
            ("Write integration tests", "qa_manager"),
            ("Setup CI/CD pipeline", "devops_lead"),
            ("Define user stories", "product_owner")
        ]
        
        for work_item, role in work_items:
            instance = team[role]
            # Verify instance is available
            available = await service.find_available_instance(
                instance.persona_type_id,
                azure_devops_config["test_project"]
            )
            assert available is not None
            assert available.id == instance.id
            
            # Simulate work
            await service.record_spend(
                instance.id,
                Decimal("5.00"),
                work_item
            )
        
        # Get team statistics
        stats = await service.get_instance_statistics()
        assert stats["total_instances"] >= 6
        assert stats["active_instances"] >= 6
        assert stats["total_daily_spend"] >= Decimal("30.00")
        
        # Clean up
        for instance in team.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance.id
            )
        for persona_type in persona_types.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_type.id
            )
    
    async def test_clone_and_scale_team(self, db, clean_test_data):
        """Test cloning instances to scale a team"""
        type_repo = PersonaTypeRepository(db)
        factory = PersonaInstanceFactory(db)
        
        # Create developer persona type
        dev_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"developer-{uuid4().hex[:8]}",
            display_name="Full Stack Developer",
            category=PersonaCategory.DEVELOPMENT,
            description="Full stack development",
            base_workflow_id="wf0"
        ))
        
        # Create initial developer instance
        original_dev = await factory.create_instance(
            instance_name=f"TEST_Senior_Dev_1_{uuid4().hex[:8]}",
            persona_type_id=dev_type.id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="ScaleTest",
            repository_name="main-app",
            custom_settings={
                "experience_level": "senior",
                "specialties": ["backend", "database", "api"],
                "team": "alpha"
            },
            max_concurrent_tasks=8,
            priority_level=7
        )
        
        # Clone to create more developers
        cloned_devs = []
        for i in range(2, 5):
            clone = await factory.clone_instance(
                source_instance_id=original_dev.id,
                new_instance_name=f"TEST_Senior_Dev_{i}_{uuid4().hex[:8]}"
            )
            cloned_devs.append(clone)
        
        # Verify clones
        assert len(cloned_devs) == 3
        for clone in cloned_devs:
            assert clone.persona_type_id == original_dev.persona_type_id
            assert clone.azure_devops_project == original_dev.azure_devops_project
            assert clone.custom_settings["experience_level"] == "senior"
            assert clone.max_concurrent_tasks == 8
        
        # Clean up
        all_instances = [original_dev] + cloned_devs
        for instance in all_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance.id
            )
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            dev_type.id
        )
    
    async def test_factory_error_handling(self, db, clean_test_data):
        """Test factory error handling and recovery"""
        factory = PersonaInstanceFactory(db)
        
        # Test invalid persona type name in team config
        with pytest.raises(ValueError, match="persona_type_name required"):
            await factory.create_team_instances(
                project_name="Error Test",
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="ErrorTest",
                team_config={
                    "developer": {
                        # Missing persona_type_name
                        "repository": "test-repo"
                    }
                }
            )
        
        # Test non-existent persona type
        with pytest.raises(ValueError, match="Persona type .* not found"):
            await factory.create_team_instances(
                project_name="Error Test",
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="ErrorTest",
                team_config={
                    "developer": {
                        "persona_type_name": "non-existent-type"
                    }
                }
            )
        
        # Test clone of non-existent instance
        with pytest.raises(ValueError, match="Source instance .* not found"):
            await factory.clone_instance(
                source_instance_id=uuid4(),
                new_instance_name="Clone Test"
            )