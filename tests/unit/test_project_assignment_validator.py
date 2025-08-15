"""
Unit tests for Project Assignment Validator
"""

import pytest
from uuid import uuid4, UUID
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from datetime import datetime

from backend.services.project_assignment_validator import (
    ProjectAssignmentValidator,
    ValidationSeverity,
    ValidationResult,
    ProjectAssignmentValidation
)
from backend.models.persona_type import PersonaType, PersonaCategory


@pytest.mark.asyncio
class TestProjectAssignmentValidator:
    """Test project assignment validation functionality"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database manager"""
        db = AsyncMock()
        return db
    
    @pytest.fixture
    def validator(self, mock_db):
        """Create validator instance"""
        return ProjectAssignmentValidator(mock_db)
    
    @pytest.fixture
    def sample_persona_type(self):
        """Sample persona type for testing"""
        return PersonaType(
            id=uuid4(),
            type_name="senior-developer",
            display_name="Senior Developer",
            category=PersonaCategory.DEVELOPMENT,
            description="Test senior developer",
            base_workflow_id="wf1",
            capabilities=["coding", "review"],
            default_llm_config={}
        )
    
    async def test_validate_azure_devops_org_valid_url(self, validator):
        """Test validation with valid Azure DevOps organization URL"""
        valid_urls = [
            "https://dev.azure.com/testorg",
            "https://testorg.visualstudio.com",
            "dev.azure.com/testorg"  # Should be normalized
        ]
        
        for url in valid_urls:
            results = await validator._validate_azure_devops_org(url)
            assert any(r.rule_name == "org_accessibility" for r in results)
            assert not any(r.severity == ValidationSeverity.ERROR for r in results)
    
    async def test_validate_azure_devops_org_invalid_url(self, validator):
        """Test validation with invalid Azure DevOps organization URL"""
        invalid_urls = [
            "",
            "not-a-url",
            "https://github.com/testorg",
            "ftp://dev.azure.com/testorg"
        ]
        
        for url in invalid_urls:
            results = await validator._validate_azure_devops_org(url)
            error_results = [r for r in results if r.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]]
            assert len(error_results) > 0
    
    async def test_validate_azure_devops_project_valid(self, validator):
        """Test validation with valid project names"""
        valid_names = [
            "My Project",
            "test-project_123",
            "AI-Personas-Test-Sandbox-2"
        ]
        
        for name in valid_names:
            results = await validator._validate_azure_devops_project(
                "https://dev.azure.com/test", name
            )
            error_results = [r for r in results if r.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]]
            assert len(error_results) == 0
    
    async def test_validate_azure_devops_project_invalid(self, validator):
        """Test validation with invalid project names"""
        invalid_names = [
            "",  # Empty
            "x" * 65,  # Too long
            "project@#$%",  # Invalid characters
            "project\nwith\nnewlines"  # Newlines
        ]
        
        for name in invalid_names:
            results = await validator._validate_azure_devops_project(
                "https://dev.azure.com/test", name
            )
            error_results = [r for r in results if r.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]]
            assert len(error_results) > 0
    
    async def test_validate_project_capacity_within_limits(self, validator, mock_db, sample_persona_type):
        """Test capacity validation when within limits"""
        # Mock database to return current count below limit
        mock_db.execute_query.return_value = [
            {"type_name": "senior-developer", "count": 2}
        ]
        
        results = await validator._validate_project_capacity(
            sample_persona_type, "test-project"
        )
        
        # Should not have capacity errors
        capacity_errors = [r for r in results if r.rule_name == "max_personas_exceeded"]
        assert len(capacity_errors) == 0
    
    async def test_validate_project_capacity_exceeded(self, validator, mock_db, sample_persona_type):
        """Test capacity validation when limit exceeded"""
        # Mock database to return count at limit
        mock_db.execute_query.return_value = [
            {"type_name": "senior-developer", "count": 5}  # At limit
        ]
        
        results = await validator._validate_project_capacity(
            sample_persona_type, "test-project"
        )
        
        # Should have capacity error
        capacity_errors = [r for r in results if r.rule_name == "max_personas_exceeded"]
        assert len(capacity_errors) > 0
        assert capacity_errors[0].severity == ValidationSeverity.ERROR
        assert not capacity_errors[0].can_proceed
    
    async def test_validate_project_capacity_warning_threshold(self, validator, mock_db, sample_persona_type):
        """Test capacity validation at warning threshold"""
        # Mock database to return count at 80% of limit (4 out of 5)
        mock_db.execute_query.return_value = [
            {"type_name": "senior-developer", "count": 4}
        ]
        
        results = await validator._validate_project_capacity(
            sample_persona_type, "test-project"
        )
        
        # Should have warning but not error
        warnings = [r for r in results if r.rule_name == "approaching_persona_limit"]
        errors = [r for r in results if r.rule_name == "max_personas_exceeded"]
        
        assert len(warnings) > 0
        assert len(errors) == 0
        assert warnings[0].severity == ValidationSeverity.WARNING
    
    async def test_validate_team_composition_no_conflicts(self, validator, mock_db, sample_persona_type):
        """Test team composition validation with no conflicts"""
        # Mock database to return compatible existing team
        mock_db.execute_query.return_value = [
            {
                "type_name": "qa-engineer",
                "display_name": "QA Engineer",
                "count": 1,
                "instance_names": ["QA Bot"]
            }
        ]
        
        results = await validator._validate_team_composition(
            sample_persona_type, "test-project"
        )
        
        # Should not have RACI conflicts
        conflicts = [r for r in results if r.rule_name == "raci_conflict"]
        assert len(conflicts) == 0
    
    async def test_validate_team_composition_with_conflicts(self, validator, mock_db):
        """Test team composition validation with RACI conflicts"""
        # Create persona type that conflicts (second product owner)
        product_owner_type = PersonaType(
            id=uuid4(),
            type_name="product-owner",
            display_name="Product Owner",
            category=PersonaCategory.MANAGEMENT,
            description="Product Owner",
            base_workflow_id="wf5",
            capabilities=["product_management"],
            default_llm_config={}
        )
        
        # Mock database to return existing product owner
        mock_db.execute_query.return_value = [
            {
                "type_name": "product-owner",
                "display_name": "Product Owner",
                "count": 1,
                "instance_names": ["Existing PO"]
            }
        ]
        
        results = await validator._validate_team_composition(
            product_owner_type, "test-project"
        )
        
        # Should have RACI conflict
        conflicts = [r for r in results if r.rule_name == "raci_conflict"]
        assert len(conflicts) > 0
        assert conflicts[0].severity == ValidationSeverity.ERROR
        assert not conflicts[0].can_proceed
    
    async def test_validate_repository_access_valid_name(self, validator):
        """Test repository validation with valid name"""
        valid_names = [
            "my-repo",
            "backend_api",
            "frontend.web",
            "data-pipeline-v2"
        ]
        
        for name in valid_names:
            results = await validator._validate_repository_access(
                "https://dev.azure.com/test", "test-project", name
            )
            
            # Should not have format errors
            format_errors = [r for r in results if r.rule_name in ["repo_name_length", "repo_name_characters"]]
            assert len(format_errors) == 0
    
    async def test_validate_repository_access_invalid_name(self, validator):
        """Test repository validation with invalid name"""
        invalid_names = [
            "x" * 65,  # Too long
            "repo with spaces",  # Spaces not allowed
            "repo@invalid",  # Invalid characters
            "repo/with/slashes"  # Slashes not allowed
        ]
        
        for name in invalid_names:
            results = await validator._validate_repository_access(
                "https://dev.azure.com/test", "test-project", name
            )
            
            # Should have format errors
            format_errors = [r for r in results if r.rule_name in ["repo_name_length", "repo_name_characters"]]
            assert len(format_errors) > 0
    
    async def test_validate_budget_allocation_normal(self, validator, mock_db, sample_persona_type):
        """Test budget allocation validation with normal spending"""
        # Mock database to return reasonable budget info
        mock_db.execute_query.return_value = {
            "total_daily_budget": Decimal("500.00"),
            "total_monthly_budget": Decimal("10000.00"),
            "total_daily_spend": Decimal("250.00"),
            "total_monthly_spend": Decimal("5000.00"),
            "active_instances": 10
        }
        
        results = await validator._validate_budget_allocation(
            sample_persona_type, "test-project"
        )
        
        # Should not have budget warnings for normal amounts
        budget_warnings = [r for r in results if "budget" in r.rule_name]
        high_budget_warnings = [r for r in budget_warnings if r.severity == ValidationSeverity.WARNING]
        assert len(high_budget_warnings) == 0
    
    async def test_validate_budget_allocation_high_budget(self, validator, mock_db, sample_persona_type):
        """Test budget allocation validation with high budget"""
        # Mock database to return high budget
        mock_db.execute_query.return_value = {
            "total_daily_budget": Decimal("1000.00"),
            "total_monthly_budget": Decimal("25000.00"),  # High budget
            "total_daily_spend": Decimal("800.00"),
            "total_monthly_spend": Decimal("20000.00"),
            "active_instances": 20
        }
        
        results = await validator._validate_budget_allocation(
            sample_persona_type, "test-project"
        )
        
        # Should have high budget warning
        high_budget_warnings = [r for r in results if r.rule_name == "high_project_budget"]
        assert len(high_budget_warnings) > 0
        assert high_budget_warnings[0].severity == ValidationSeverity.WARNING
    
    async def test_validate_budget_allocation_high_utilization(self, validator, mock_db, sample_persona_type):
        """Test budget allocation validation with high utilization"""
        # Mock database to return high utilization
        mock_db.execute_query.return_value = {
            "total_daily_budget": Decimal("1000.00"),
            "total_monthly_budget": Decimal("20000.00"),
            "total_daily_spend": Decimal("900.00"),
            "total_monthly_spend": Decimal("19000.00"),  # 95% utilization
            "active_instances": 15
        }
        
        results = await validator._validate_budget_allocation(
            sample_persona_type, "test-project"
        )
        
        # Should have high utilization warning
        utilization_warnings = [r for r in results if r.rule_name == "high_budget_utilization"]
        assert len(utilization_warnings) > 0
        assert utilization_warnings[0].severity == ValidationSeverity.WARNING
    
    async def test_validate_security_requirements_sensitive_role(self, validator):
        """Test security validation for security-sensitive roles"""
        # Create security-sensitive persona type
        security_type = PersonaType(
            id=uuid4(),
            type_name="devsecops-engineer",
            display_name="DevSecOps Engineer",
            category=PersonaCategory.OPERATIONS,
            description="Security operations",
            base_workflow_id="wf3",
            capabilities=["security", "operations"],
            default_llm_config={}
        )
        
        results = await validator._validate_security_requirements(
            security_type, "https://dev.azure.com/test", "test-project"
        )
        
        # Should have security notice
        security_notices = [r for r in results if r.rule_name == "security_sensitive_role"]
        assert len(security_notices) > 0
        assert security_notices[0].severity == ValidationSeverity.INFO
    
    async def test_validate_security_requirements_production_project(self, validator, sample_persona_type):
        """Test security validation for production projects"""
        production_projects = [
            "Production-API",
            "Live-Website", 
            "Prod-Backend"
        ]
        
        for project_name in production_projects:
            results = await validator._validate_security_requirements(
                sample_persona_type, "https://dev.azure.com/test", project_name
            )
            
            # Should have production warning
            prod_warnings = [r for r in results if r.rule_name == "production_project_warning"]
            assert len(prod_warnings) > 0
            assert prod_warnings[0].severity == ValidationSeverity.WARNING
    
    async def test_comprehensive_validation_success(self, validator, mock_db, sample_persona_type):
        """Test complete validation workflow with successful result"""
        # Mock database calls for successful validation
        mock_db.execute_query.side_effect = [
            # Project capacity query
            [{"type_name": "senior-developer", "count": 2}],
            # Team composition query  
            [{"type_name": "qa-engineer", "display_name": "QA Engineer", "count": 1, "instance_names": ["QA Bot"]}],
            # Budget allocation query
            {
                "total_daily_budget": Decimal("500.00"),
                "total_monthly_budget": Decimal("8000.00"),
                "total_daily_spend": Decimal("250.00"),
                "total_monthly_spend": Decimal("4000.00"),
                "active_instances": 8
            },
            # Project info query
            [{"type_name": "qa-engineer", "display_name": "QA Engineer", "count": 1, 
              "total_budget": Decimal("1000.00"), "total_spend": Decimal("500.00")}]
        ]
        
        # Mock _get_persona_type
        with patch.object(validator, '_get_persona_type', return_value=sample_persona_type):
            validation = await validator.validate_project_assignment(
                sample_persona_type.id,
                "https://dev.azure.com/test",
                "AI-Personas-Test-Sandbox-2"
            )
        
        # Should be valid with no critical errors
        assert validation.can_proceed
        assert len(validation.critical_issues) == 0
        assert len(validation.errors) == 0
        assert validation.project_info["project_name"] == "AI-Personas-Test-Sandbox-2"
    
    async def test_comprehensive_validation_failure(self, validator, mock_db):
        """Test complete validation workflow with failure result"""
        # Mock database calls for failed validation
        mock_db.execute_query.side_effect = [
            # Project capacity query - at limit
            [{"type_name": "senior-developer", "count": 5}],
            # Team composition query - conflict
            [{"type_name": "product-owner", "display_name": "Product Owner", "count": 1, "instance_names": ["PO Bot"]}],
            # Budget allocation query
            {"total_daily_budget": None, "total_monthly_budget": None, 
             "total_daily_spend": None, "total_monthly_spend": None, "active_instances": 0},
            # Project info query
            []
        ]
        
        # Create conflicting persona type
        conflicting_type = PersonaType(
            id=uuid4(),
            type_name="product-owner",
            display_name="Product Owner",
            category=PersonaCategory.MANAGEMENT,
            description="Product Owner",
            base_workflow_id="wf5",
            capabilities=["product_management"],
            default_llm_config={}
        )
        
        # Mock _get_persona_type
        with patch.object(validator, '_get_persona_type', return_value=conflicting_type):
            validation = await validator.validate_project_assignment(
                conflicting_type.id,
                "https://dev.azure.com/test",
                "test-project"
            )
        
        # Should fail validation
        assert not validation.can_proceed
        assert len(validation.errors) > 0
    
    async def test_validation_with_nonexistent_persona_type(self, validator, mock_db):
        """Test validation with non-existent persona type"""
        # Mock _get_persona_type to return None
        with patch.object(validator, '_get_persona_type', return_value=None):
            validation = await validator.validate_project_assignment(
                uuid4(),
                "https://dev.azure.com/test",
                "test-project"
            )
        
        # Should fail with critical error
        assert not validation.is_valid
        assert not validation.can_proceed
        assert len(validation.critical_issues) > 0
        assert validation.critical_issues[0].rule_name == "persona_type_exists"
    
    async def test_validation_result_severity_filtering(self, validator, mock_db, sample_persona_type):
        """Test validation result filtering by severity"""
        # Create mixed severity results
        results = [
            ValidationResult("info_rule", ValidationSeverity.INFO, "Info message"),
            ValidationResult("warning_rule", ValidationSeverity.WARNING, "Warning message"),
            ValidationResult("error_rule", ValidationSeverity.ERROR, "Error message", can_proceed=False),
            ValidationResult("critical_rule", ValidationSeverity.CRITICAL, "Critical message", can_proceed=False)
        ]
        
        validation = ProjectAssignmentValidation(
            is_valid=False,
            can_proceed=False,
            results=results,
            project_info={},
            recommendations=[]
        )
        
        # Test filtering properties
        assert len(validation.errors) == 1
        assert len(validation.warnings) == 1
        assert len(validation.critical_issues) == 1
        assert validation.errors[0].rule_name == "error_rule"
        assert validation.warnings[0].rule_name == "warning_rule"
        assert validation.critical_issues[0].rule_name == "critical_rule"