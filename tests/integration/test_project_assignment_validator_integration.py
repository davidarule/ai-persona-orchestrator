"""
Integration tests for Project Assignment Validator with real database
"""

import pytest
from uuid import uuid4
from decimal import Decimal

from backend.services.project_assignment_validator import (
    ProjectAssignmentValidator,
    ValidationSeverity
)
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.models.persona_instance import PersonaInstanceCreate, LLMProvider, LLMModel
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.persona_instance_service import PersonaInstanceService


@pytest.mark.asyncio
class TestProjectAssignmentValidatorIntegration:
    """Integration tests with real database"""
    
    @pytest.fixture
    async def validator(self, db):
        """Create validator with real database"""
        return ProjectAssignmentValidator(db)
    
    @pytest.fixture
    async def test_persona_types(self, db):
        """Create test persona types"""
        repo = PersonaTypeRepository(db)
        created_types = {}
        
        types_to_create = [
            ("senior-developer", "Senior Developer", PersonaCategory.DEVELOPMENT),
            ("qa-engineer", "QA Engineer", PersonaCategory.TESTING),
            ("product-owner", "Product Owner", PersonaCategory.MANAGEMENT),
            ("software-architect", "Software Architect", PersonaCategory.ARCHITECTURE),
            ("devsecops-engineer", "DevSecOps Engineer", PersonaCategory.OPERATIONS)
        ]
        
        for type_name, display_name, category in types_to_create:
            persona_type = await repo.create(PersonaTypeCreate(
                type_name=f"{type_name}-test-{uuid4().hex[:8]}",
                display_name=display_name,
                category=category,
                description=f"Test {display_name}",
                base_workflow_id="wf0"
            ))
            created_types[type_name] = persona_type
        
        yield created_types
        
        # Cleanup
        for persona_type in created_types.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_type.id
            )
    
    async def test_validate_empty_project_assignment(self, validator, test_persona_types):
        """Test validation for first persona in an empty project"""
        validation = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["senior-developer"].id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project=f"EmptyProject-{uuid4().hex[:8]}"
        )
        
        # Should succeed for empty project
        assert validation.can_proceed
        assert len(validation.critical_issues) == 0
        assert len(validation.errors) == 0
        
        # Should have info about being first team member
        first_member_info = [r for r in validation.results if r.rule_name == "first_team_member"]
        assert len(first_member_info) > 0
        assert first_member_info[0].severity == ValidationSeverity.INFO
        
        # Project info should show empty team
        assert validation.project_info["total_team_size"] == 0
    
    async def test_validate_project_with_existing_team(self, validator, test_persona_types, db, azure_devops_config):
        """Test validation for project with existing team members"""
        project_name = f"TeamProject-{uuid4().hex[:8]}"
        service = PersonaInstanceService(db)
        created_instances = []
        
        # Create existing team members
        existing_members = [
            ("qa-engineer", "QA Bot"),
            ("software-architect", "Architect Bot")
        ]
        
        for persona_key, instance_name in existing_members:
            instance = await service.create_instance(PersonaInstanceCreate(
                instance_name=f"{instance_name}-{uuid4().hex[:8]}",
                persona_type_id=test_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=project_name,
                llm_providers=[LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY"
                )],
                spend_limit_daily=Decimal("50.00"),
                spend_limit_monthly=Decimal("1000.00")
            ))
            created_instances.append(instance.id)
        
        # Now validate adding a senior developer
        validation = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["senior-developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name
        )
        
        # Should succeed - no conflicts
        assert validation.can_proceed
        assert len(validation.errors) == 0
        
        # Project info should show existing team
        assert validation.project_info["total_team_size"] == 2
        assert len(validation.project_info["team_composition"]) == 2
        
        # Cleanup
        for instance_id in created_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
    
    async def test_validate_raci_conflict_detection(self, validator, test_persona_types, db, azure_devops_config):
        """Test RACI conflict detection with real data"""
        project_name = f"ConflictProject-{uuid4().hex[:8]}"
        service = PersonaInstanceService(db)
        
        # Create first product owner
        first_po = await service.create_instance(PersonaInstanceCreate(
            instance_name=f"FirstPO-{uuid4().hex[:8]}",
            persona_type_id=test_persona_types["product-owner"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name,
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("75.00"),
            spend_limit_monthly=Decimal("1500.00")
        ))
        
        # Try to add second product owner - should conflict
        validation = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["product-owner"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name
        )
        
        # Should have RACI conflict
        assert not validation.can_proceed
        conflicts = [r for r in validation.results if r.rule_name == "raci_conflict"]
        assert len(conflicts) > 0
        assert conflicts[0].severity == ValidationSeverity.ERROR
        assert not conflicts[0].can_proceed
        
        # Cleanup
        await db.execute_query(
            "DELETE FROM orchestrator.persona_instances WHERE id = $1",
            first_po.id
        )
    
    async def test_validate_capacity_limits_enforcement(self, validator, test_persona_types, db, azure_devops_config):
        """Test capacity limit enforcement with real instances"""
        project_name = f"CapacityProject-{uuid4().hex[:8]}"
        service = PersonaInstanceService(db)
        created_instances = []
        
        # Create maximum allowed senior developers (5)
        max_allowed = validator.MAX_PERSONAS_PER_PROJECT.get("senior-developer", 5)
        
        for i in range(max_allowed):
            instance = await service.create_instance(PersonaInstanceCreate(
                instance_name=f"Developer-{i}-{uuid4().hex[:8]}",
                persona_type_id=test_persona_types["senior-developer"].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=project_name,
                llm_providers=[LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY"
                )],
                spend_limit_daily=Decimal("50.00"),
                spend_limit_monthly=Decimal("1000.00")
            ))
            created_instances.append(instance.id)
        
        # Try to add one more - should exceed capacity
        validation = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["senior-developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name
        )
        
        # Should have capacity error
        assert not validation.can_proceed
        capacity_errors = [r for r in validation.results if r.rule_name == "max_personas_exceeded"]
        assert len(capacity_errors) > 0
        assert capacity_errors[0].severity == ValidationSeverity.ERROR
        assert capacity_errors[0].details["current_count"] == max_allowed
        
        # Cleanup
        for instance_id in created_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
    
    async def test_validate_update_scenario_excludes_self(self, validator, test_persona_types, db, azure_devops_config):
        """Test that validation excludes the instance being updated"""
        project_name = f"UpdateProject-{uuid4().hex[:8]}"
        service = PersonaInstanceService(db)
        
        # Create an instance
        instance = await service.create_instance(PersonaInstanceCreate(
            instance_name=f"UpdateBot-{uuid4().hex[:8]}",
            persona_type_id=test_persona_types["senior-developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name,
            llm_providers=[LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                api_key_env_var="OPENAI_API_KEY"
            )],
            spend_limit_daily=Decimal("50.00"),
            spend_limit_monthly=Decimal("1000.00")
        ))
        
        # Validate updating the same instance (should exclude itself from counts)
        validation = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["senior-developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name,
            instance_id=instance.id  # Exclude self
        )
        
        # Should succeed since we exclude the instance being updated
        assert validation.can_proceed
        assert len(validation.errors) == 0
        
        # Should show as first team member since we exclude self
        first_member_info = [r for r in validation.results if r.rule_name == "first_team_member"]
        assert len(first_member_info) > 0
        
        # Cleanup
        await db.execute_query(
            "DELETE FROM orchestrator.persona_instances WHERE id = $1",
            instance.id
        )
    
    async def test_validate_budget_analysis_with_real_data(self, validator, test_persona_types, db, azure_devops_config):
        """Test budget analysis with real spending data"""
        project_name = f"BudgetProject-{uuid4().hex[:8]}"
        service = PersonaInstanceService(db)
        created_instances = []
        
        # Create instances with varying budget allocations
        budget_configs = [
            (Decimal("200.00"), Decimal("4000.00")),  # High budget
            (Decimal("100.00"), Decimal("2000.00")),  # Medium budget
            (Decimal("50.00"), Decimal("1000.00"))    # Normal budget
        ]
        
        for i, (daily_limit, monthly_limit) in enumerate(budget_configs):
            instance = await service.create_instance(PersonaInstanceCreate(
                instance_name=f"BudgetBot-{i}-{uuid4().hex[:8]}",
                persona_type_id=test_persona_types["senior-developer"].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=project_name,
                llm_providers=[LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY"
                )],
                spend_limit_daily=daily_limit,
                spend_limit_monthly=monthly_limit
            ))
            created_instances.append(instance.id)
            
            # Add some spending to simulate utilization
            await service.record_spend(instance.id, monthly_limit * Decimal("0.5"), "Test spending")
        
        # Validate adding another instance
        validation = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["qa-engineer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name
        )
        
        # Should have budget analysis
        assert validation.can_proceed
        
        # Project info should include budget details
        total_budget = validation.project_info["total_monthly_budget"]
        total_spend = validation.project_info["total_monthly_spend"]
        assert total_budget > 5000  # Should be substantial
        assert total_spend > 0      # Should have some spending
        
        # May have budget warnings if total is high
        budget_warnings = [r for r in validation.results if "budget" in r.rule_name]
        if total_budget > 10000:
            assert any(r.rule_name == "high_project_budget" for r in budget_warnings)
        
        # Cleanup
        for instance_id in created_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
    
    async def test_validate_security_requirements_integration(self, validator, test_persona_types):
        """Test security requirements validation"""
        # Test security-sensitive role
        validation = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["devsecops-engineer"].id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="SecurityProject"
        )
        
        # Should have security notice
        security_notices = [r for r in validation.results if r.rule_name == "security_sensitive_role"]
        assert len(security_notices) > 0
        assert security_notices[0].severity == ValidationSeverity.INFO
        
        # Test production project warning
        validation_prod = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["senior-developer"].id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="Production-API"
        )
        
        prod_warnings = [r for r in validation_prod.results if r.rule_name == "production_project_warning"]
        assert len(prod_warnings) > 0
        assert prod_warnings[0].severity == ValidationSeverity.WARNING
    
    async def test_validate_repository_access_integration(self, validator, test_persona_types):
        """Test repository access validation"""
        # Test valid repository names
        valid_repos = ["backend-api", "frontend_web", "data.pipeline"]
        
        for repo_name in valid_repos:
            validation = await validator.validate_project_assignment(
                persona_type_id=test_persona_types["senior-developer"].id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="TestProject",
                repository_name=repo_name
            )
            
            # Should not have repository format errors
            repo_errors = [r for r in validation.results 
                          if r.rule_name in ["repo_name_length", "repo_name_characters"]]
            assert len(repo_errors) == 0
        
        # Test invalid repository name
        validation_invalid = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["senior-developer"].id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="TestProject",
            repository_name="invalid repo name with spaces"
        )
        
        # Should have repository format error
        repo_errors = [r for r in validation_invalid.results 
                      if r.rule_name in ["repo_name_length", "repo_name_characters"]]
        assert len(repo_errors) > 0
    
    async def test_validate_comprehensive_workflow(self, validator, test_persona_types, db, azure_devops_config):
        """Test complete validation workflow with mixed scenarios"""
        project_name = f"ComprehensiveProject-{uuid4().hex[:8]}"
        service = PersonaInstanceService(db)
        created_instances = []
        
        # Create a diverse team
        team_setup = [
            ("software-architect", "Chief Architect", Decimal("150.00"), Decimal("3000.00")),
            ("senior-developer", "Backend Lead", Decimal("100.00"), Decimal("2000.00")),
            ("qa-engineer", "QA Lead", Decimal("75.00"), Decimal("1500.00"))
        ]
        
        for persona_key, instance_name, daily_limit, monthly_limit in team_setup:
            instance = await service.create_instance(PersonaInstanceCreate(
                instance_name=f"{instance_name}-{uuid4().hex[:8]}",
                persona_type_id=test_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=project_name,
                repository_name="main-app",
                llm_providers=[LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )],
                spend_limit_daily=daily_limit,
                spend_limit_monthly=monthly_limit
            ))
            created_instances.append(instance.id)
            
            # Add varied spending
            spend_amount = monthly_limit * Decimal("0.3")
            await service.record_spend(instance.id, spend_amount, f"Work on {instance_name}")
        
        # Validate adding another senior developer (should be fine)
        validation = await validator.validate_project_assignment(
            persona_type_id=test_persona_types["senior-developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=project_name,
            repository_name="frontend-app"
        )
        
        # Should succeed
        assert validation.can_proceed
        assert validation.is_valid or len(validation.errors) == 0
        
        # Should have comprehensive project info
        assert validation.project_info["total_team_size"] == 3
        assert validation.project_info["total_monthly_budget"] > 5000
        assert validation.project_info["total_monthly_spend"] > 0
        
        # Should have recommendations
        assert len(validation.recommendations) > 0
        
        # Team composition should be detailed
        team_composition = validation.project_info["team_composition"]
        assert len(team_composition) == 3
        architect_info = next((t for t in team_composition if "architect" in t["type_name"]), None)
        assert architect_info is not None
        assert architect_info["monthly_budget"] == 3000.0
        
        # Cleanup
        for instance_id in created_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )