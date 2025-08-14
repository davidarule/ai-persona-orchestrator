"""
Unit tests for PersonaInstanceFactory
"""

import pytest
from uuid import uuid4
from decimal import Decimal

from backend.factories.persona_instance_factory import PersonaInstanceFactory
from backend.models.persona_instance import LLMProvider, LLMModel
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.asyncio
class TestPersonaInstanceFactory:
    """Test PersonaInstanceFactory functionality"""
    
    async def test_create_instance_with_defaults(self, db, clean_test_data):
        """Test creating instance with default configurations"""
        # Create a software architect persona type
        type_repo = PersonaTypeRepository(db)
        persona_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"software-architect-{uuid4().hex[:8]}",
            display_name="Software Architect",
            category=PersonaCategory.ARCHITECTURE,
            description="Test architect",
            base_workflow_id="wf0"
        ))
        
        factory = PersonaInstanceFactory(db)
        
        # Create instance with minimal params
        instance = await factory.create_instance(
            instance_name=f"TEST_Architect_{uuid4().hex[:8]}",
            persona_type_id=persona_type.id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="TestProject"
        )
        
        # Verify defaults were applied
        assert instance is not None
        assert len(instance.llm_providers) == 2  # Architecture category gets 2 providers
        assert instance.llm_providers[0].provider == LLMProvider.OPENAI
        assert instance.llm_providers[0].model_name == "gpt-4-turbo-preview"
        assert instance.spend_limit_daily == Decimal("100.00")  # Architecture default
        assert instance.spend_limit_monthly == Decimal("2000.00")
        # Since type_name is unique, it won't match PERSONA_SETTINGS
        # But we should have category and workflow settings
        assert instance.custom_settings["persona_category"] == "architecture"
        assert instance.custom_settings["base_workflow_id"] == "wf0"
    
    async def test_create_instance_with_custom_config(self, db, test_persona_type_id, clean_test_data):
        """Test creating instance with custom configurations"""
        factory = PersonaInstanceFactory(db)
        
        custom_llm = [
            LLMModel(
                provider=LLMProvider.ANTHROPIC,
                model_name="claude-3",
                temperature=0.3,
                api_key_env_var="ANTHROPIC_API_KEY"
            )
        ]
        
        custom_limits = {
            "daily": Decimal("200.00"),
            "monthly": Decimal("4000.00")
        }
        
        custom_settings = {
            "custom_field": "custom_value",
            "priority_focus": ["performance", "security"]
        }
        
        instance = await factory.create_instance(
            instance_name=f"TEST_Custom_{uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="CustomProject",
            repository_name="custom-repo",
            custom_llm_providers=custom_llm,
            custom_spend_limits=custom_limits,
            custom_settings=custom_settings,
            max_concurrent_tasks=10,
            priority_level=5
        )
        
        # Verify custom config was applied
        assert len(instance.llm_providers) == 1
        assert instance.llm_providers[0].provider == LLMProvider.ANTHROPIC
        assert instance.spend_limit_daily == Decimal("200.00")
        assert instance.spend_limit_monthly == Decimal("4000.00")
        assert instance.max_concurrent_tasks == 10
        assert instance.priority_level == 5
        assert instance.custom_settings["custom_field"] == "custom_value"
    
    async def test_create_team_instances(self, db, clean_test_data):
        """Test creating a team of instances"""
        # Create required persona types
        type_repo = PersonaTypeRepository(db)
        
        architect_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"software-architect-{uuid4().hex[:8]}",
            display_name="Software Architect",
            category=PersonaCategory.ARCHITECTURE,
            description="Architect",
            base_workflow_id="wf0"
        ))
        
        backend_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"backend-developer-{uuid4().hex[:8]}",
            display_name="Backend Developer",
            category=PersonaCategory.DEVELOPMENT,
            description="Backend Dev",
            base_workflow_id="wf0"
        ))
        
        factory = PersonaInstanceFactory(db)
        
        team_config = {
            "architect": {
                "persona_type_name": architect_type.type_name,
                "repository": "architecture-docs",
                "priority": 10
            },
            "backend_lead": {
                "persona_type_name": backend_type.type_name,
                "repository": "backend-api",
                "priority": 8,
                "max_tasks": 10
            }
        }
        
        team = await factory.create_team_instances(
            project_name=f"Test Project {uuid4().hex[:8]}",
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="TeamTest",
            team_config=team_config
        )
        
        # Verify team was created
        assert len(team) == 2
        assert "architect" in team
        assert "backend_lead" in team
        
        # Verify architect instance
        architect = team["architect"]
        assert architect.instance_name.startswith("Architect - Test Project")
        assert architect.repository_name == "architecture-docs"
        assert architect.priority_level == 10
        
        # Verify backend lead instance
        backend = team["backend_lead"]
        assert backend.instance_name.startswith("Backend Lead - Test Project")
        assert backend.repository_name == "backend-api"
        assert backend.priority_level == 8
        assert backend.max_concurrent_tasks == 10
    
    @pytest.mark.skip(reason="Standard team requires pre-existing persona types")
    async def test_create_standard_development_team(self, db, clean_test_data):
        """Test creating a standard development team"""
        # Create required persona types for medium team
        type_repo = PersonaTypeRepository(db)
        
        unique_suffix = uuid4().hex[:8]
        types_to_create = [
            (f"software-architect-{unique_suffix}", "Software Architect", PersonaCategory.ARCHITECTURE),
            (f"backend-developer-{unique_suffix}", "Backend Developer", PersonaCategory.DEVELOPMENT),
            (f"frontend-developer-{unique_suffix}", "Frontend Developer", PersonaCategory.DEVELOPMENT),
            (f"qa-engineer-{unique_suffix}", "QA Engineer", PersonaCategory.TESTING),
            (f"devsecops-engineer-{unique_suffix}", "DevSecOps Engineer", PersonaCategory.OPERATIONS)
        ]
        
        for type_name, display_name, category in types_to_create:
            await type_repo.create(PersonaTypeCreate(
                type_name=type_name,
                display_name=display_name,
                category=category,
                description=f"Test {display_name}",
                base_workflow_id="wf0"
            ))
        
        factory = PersonaInstanceFactory(db)
        
        # Create medium team
        team = await factory.create_standard_development_team(
            project_name="Standard Project",
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="StandardTeam",
            team_size="medium"
        )
        
        # Verify medium team composition
        assert len(team) == 5
        expected_roles = ["architect", "backend_lead", "frontend_lead", "qa_lead", "devops_engineer"]
        for role in expected_roles:
            assert role in team
            assert team[role] is not None
        
        # Verify priorities
        assert team["architect"].priority_level == 10
        assert team["backend_lead"].priority_level == 8
        assert team["frontend_lead"].priority_level == 8
        assert team["qa_lead"].priority_level == 7
        assert team["devops_engineer"].priority_level == 6
    
    async def test_clone_instance(self, db, test_persona_type_id, clean_test_data):
        """Test cloning an existing instance"""
        factory = PersonaInstanceFactory(db)
        
        # Create original instance
        original = await factory.create_instance(
            instance_name=f"TEST_Original_{uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="OriginalProject",
            repository_name="original-repo",
            custom_settings={"env": "production", "feature": "enabled"},
            max_concurrent_tasks=8,
            priority_level=7
        )
        
        # Clone it
        clone = await factory.clone_instance(
            source_instance_id=original.id,
            new_instance_name=f"TEST_Clone_{uuid4().hex[:8]}",
            new_project="CloneProject",
            new_repository="clone-repo"
        )
        
        # Verify clone
        assert clone.id != original.id
        assert clone.instance_name != original.instance_name
        assert clone.persona_type_id == original.persona_type_id
        assert clone.azure_devops_project == "CloneProject"
        assert clone.repository_name == "clone-repo"
        assert clone.max_concurrent_tasks == original.max_concurrent_tasks
        assert clone.priority_level == original.priority_level
        assert clone.custom_settings == original.custom_settings
        assert len(clone.llm_providers) == len(original.llm_providers)
    
    async def test_factory_with_invalid_persona_type(self, db, clean_test_data):
        """Test factory handles invalid persona type gracefully"""
        factory = PersonaInstanceFactory(db)
        
        with pytest.raises(ValueError, match="Persona type .* not found"):
            await factory.create_instance(
                instance_name="TEST_Invalid",
                persona_type_id=uuid4(),  # Non-existent ID
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="TestProject"
            )
    
    async def test_factory_applies_category_defaults(self, db, clean_test_data):
        """Test factory applies correct defaults based on category"""
        type_repo = PersonaTypeRepository(db)
        factory = PersonaInstanceFactory(db)
        
        # Test different categories
        test_cases = [
            (PersonaCategory.DEVELOPMENT, f"dev-test-{uuid4().hex[:8]}", "Development Test", 1, Decimal("75.00")),
            (PersonaCategory.TESTING, f"qa-test-{uuid4().hex[:8]}", "QA Test", 1, Decimal("50.00")),
            (PersonaCategory.OPERATIONS, f"ops-test-{uuid4().hex[:8]}", "Ops Test", 1, Decimal("75.00"))
        ]
        
        for category, type_name, display_name, expected_llm_count, expected_daily_limit in test_cases:
            # Create persona type
            persona_type = await type_repo.create(PersonaTypeCreate(
                type_name=type_name,
                display_name=display_name,
                category=category,
                description=f"Test {category}",
                base_workflow_id="wf0"
            ))
            
            # Create instance
            instance = await factory.create_instance(
                instance_name=f"TEST_{category}_{uuid4().hex[:8]}",
                persona_type_id=persona_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="CategoryTest"
            )
            
            # Verify category-specific defaults
            assert len(instance.llm_providers) == expected_llm_count
            assert instance.spend_limit_daily == expected_daily_limit