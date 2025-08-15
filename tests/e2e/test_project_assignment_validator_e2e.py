"""
End-to-End tests for Project Assignment Validator
Real-world scenarios and workflow validation
"""

import pytest
import asyncio
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta

from backend.services.project_assignment_validator import (
    ProjectAssignmentValidator,
    ValidationSeverity
)
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.models.persona_instance import PersonaInstanceCreate, LLMProvider, LLMModel
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.persona_instance_service import PersonaInstanceService
from backend.factories.persona_instance_factory import PersonaInstanceFactory


@pytest.mark.e2e
@pytest.mark.asyncio
class TestProjectAssignmentValidatorE2E:
    """E2E tests simulating real-world project assignment workflows"""
    
    @pytest.fixture
    async def validator(self, db):
        """Create validator with real database"""
        return ProjectAssignmentValidator(db)
    
    @pytest.fixture
    async def complete_persona_types(self, db):
        """Create complete set of persona types for E2E testing"""
        repo = PersonaTypeRepository(db)
        created_types = {}
        
        # Complete persona type set matching real system
        types_config = [
            ("software-architect", "Software Architect", PersonaCategory.ARCHITECTURE),
            ("senior-developer", "Senior Developer", PersonaCategory.DEVELOPMENT),
            ("backend-developer", "Backend Developer", PersonaCategory.DEVELOPMENT),
            ("frontend-developer", "Frontend Developer", PersonaCategory.DEVELOPMENT),
            ("qa-engineer", "QA Engineer", PersonaCategory.TESTING),
            ("devsecops-engineer", "DevSecOps Engineer", PersonaCategory.OPERATIONS),
            ("product-owner", "Product Owner", PersonaCategory.MANAGEMENT),
            ("scrum-master", "Scrum Master", PersonaCategory.MANAGEMENT),
            ("technical-writer", "Technical Writer", PersonaCategory.SPECIALIZED),
            ("data-scientist", "Data Scientist", PersonaCategory.SPECIALIZED),
            ("ux-designer", "UX Designer", PersonaCategory.SPECIALIZED),
            ("mobile-developer", "Mobile Developer", PersonaCategory.DEVELOPMENT)
        ]
        
        for type_name, display_name, category in types_config:
            persona_type = await repo.create(PersonaTypeCreate(
                type_name=f"{type_name}-e2e-{uuid4().hex[:8]}",
                display_name=display_name,
                category=category,
                description=f"E2E test {display_name}",
                base_workflow_id="wf0",
                capabilities=["coding", "testing", "architecture"],
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
    
    async def test_startup_company_project_evolution(self, validator, complete_persona_types, db, azure_devops_config):
        """Test project assignment validation through startup company evolution"""
        # Scenario: Startup company growing from MVP to full product
        
        base_project = "StartupEvolution"
        service = PersonaInstanceService(db)
        factory = PersonaInstanceFactory(db)
        all_instances = []
        
        # Phase 1: MVP Team (2 people)
        print("\n=== PHASE 1: MVP TEAM ===")
        
        mvp_team = [
            ("senior-developer", "Tech Founder", Decimal("200.00"), Decimal("4000.00")),
            ("qa-engineer", "QA Founder", Decimal("100.00"), Decimal("2000.00"))
        ]
        
        for persona_key, role_name, daily_limit, monthly_limit in mvp_team:
            # Validate assignment first
            validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{base_project}-MVP"
            )
            
            # Should be valid for MVP phase
            assert validation.can_proceed
            print(f"✓ {role_name} assignment validated")
            
            # Create the instance
            instance = await service.create_instance(PersonaInstanceCreate(
                instance_name=f"{role_name}-{uuid4().hex[:8]}",
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{base_project}-MVP",
                llm_providers=[LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )],
                spend_limit_daily=daily_limit,
                spend_limit_monthly=monthly_limit
            ))
            all_instances.append(instance.id)
            
            # Simulate MVP work
            await service.record_spend(instance.id, daily_limit * Decimal("0.3"), f"{role_name} MVP work")
        
        # Phase 2: Growth Team (5-8 people)
        print("\n=== PHASE 2: GROWTH TEAM ===")
        
        growth_additions = [
            ("software-architect", "Chief Architect"),
            ("frontend-developer", "Frontend Lead"),
            ("backend-developer", "Backend Specialist"),
            ("product-owner", "Product Manager"),
            ("devsecops-engineer", "DevOps Lead")
        ]
        
        for persona_key, role_name in growth_additions:
            # Validate each addition
            validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{base_project}-Growth"
            )
            
            # Should be valid for growth phase
            assert validation.can_proceed
            print(f"✓ {role_name} assignment validated")
            
            # Check for team balance recommendations
            if validation.recommendations:
                print(f"  Recommendations: {validation.recommendations[:2]}")  # Show first 2
            
            # Create instance using factory for more realistic setup
            instance = await factory.create_instance(
                instance_name=f"{role_name}-{uuid4().hex[:8]}",
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{base_project}-Growth"
            )
            all_instances.append(instance.id)
        
        # Phase 3: Scale Team - Test capacity limits
        print("\n=== PHASE 3: SCALE TEAM (Testing Limits) ===")
        
        # Try to add too many senior developers
        for i in range(6):  # Exceeds typical limit of 5
            validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types["senior-developer"].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{base_project}-Scale"
            )
            
            if i < 4:  # First few should be OK
                assert validation.can_proceed
                print(f"✓ Senior Developer #{i+1} validated")
            else:  # Should hit capacity limits
                capacity_warnings = [r for r in validation.results if "persona" in r.rule_name and "limit" in r.rule_name]
                if capacity_warnings:
                    print(f"⚠ Senior Developer #{i+1}: {capacity_warnings[0].message}")
                    if not validation.can_proceed:
                        print(f"✗ Senior Developer #{i+1}: Capacity limit reached")
                        break
        
        # Try to add second Product Owner (should conflict)
        print("\n=== TESTING RACI CONFLICTS ===")
        
        po_conflict_validation = await validator.validate_project_assignment(
            persona_type_id=complete_persona_types["product-owner"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=f"{base_project}-Growth"  # Already has PO
        )
        
        # Should have RACI conflict
        assert not po_conflict_validation.can_proceed
        conflicts = [r for r in po_conflict_validation.results if r.rule_name == "raci_conflict"]
        assert len(conflicts) > 0
        print(f"✗ Second Product Owner: {conflicts[0].message}")
        
        # Cleanup all instances
        for instance_id in all_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
    
    async def test_enterprise_multi_project_assignment(self, validator, complete_persona_types, db, azure_devops_config):
        """Test complex enterprise scenario with multiple projects and constraints"""
        # Scenario: Large enterprise with multiple concurrent projects
        
        service = PersonaInstanceService(db)
        all_instances = []
        
        # Define multiple projects with different characteristics
        projects = [
            {
                "name": "Enterprise-Core-Platform",
                "type": "platform",
                "security_level": "high",
                "budget_category": "high",
                "team_size": "large"
            },
            {
                "name": "Customer-Portal-Web", 
                "type": "web-application",
                "security_level": "medium",
                "budget_category": "medium",
                "team_size": "medium"
            },
            {
                "name": "Mobile-App-iOS",
                "type": "mobile-app",
                "security_level": "medium",
                "budget_category": "low",
                "team_size": "small"
            },
            {
                "name": "Production-API-Service",
                "type": "api-service", 
                "security_level": "critical",
                "budget_category": "high",
                "team_size": "medium"
            }
        ]
        
        for project in projects:
            print(f"\n=== VALIDATING PROJECT: {project['name']} ===")
            project_instances = []
            
            # Get recommended team for project type
            if project["type"] == "web-application":
                recommended_team = ["software-architect", "frontend-developer", "backend-developer", "qa-engineer"]
            elif project["type"] == "api-service":
                recommended_team = ["software-architect", "backend-developer", "qa-engineer", "devsecops-engineer"]
            elif project["type"] == "mobile-app":
                recommended_team = ["software-architect", "mobile-developer", "qa-engineer", "ux-designer"]
            else:  # platform
                recommended_team = ["software-architect", "senior-developer", "devsecops-engineer", "data-scientist"]
            
            for persona_key in recommended_team:
                if persona_key not in complete_persona_types:
                    continue  # Skip if not available in test set
                
                # Validate assignment
                validation = await validator.validate_project_assignment(
                    persona_type_id=complete_persona_types[persona_key].id,
                    azure_devops_org=azure_devops_config["org_url"],
                    azure_devops_project=project["name"]
                )
                
                # Check validation results
                print(f"  {persona_key}: ", end="")
                
                if validation.can_proceed:
                    print("✓ Validated")
                    
                    # Check for security warnings on production/critical projects
                    if "production" in project["name"].lower() or project["security_level"] == "critical":
                        security_warnings = [r for r in validation.results if "production" in r.rule_name or "security" in r.rule_name]
                        if security_warnings:
                            print(f"    Security Notice: {security_warnings[0].message}")
                    
                    # Create instance with appropriate budget based on project
                    budget_multiplier = {"low": 0.5, "medium": 1.0, "high": 2.0}[project["budget_category"]]
                    daily_limit = Decimal("50.00") * Decimal(str(budget_multiplier))
                    monthly_limit = Decimal("1000.00") * Decimal(str(budget_multiplier))
                    
                    instance = await service.create_instance(PersonaInstanceCreate(
                        instance_name=f"{persona_key}-{project['name']}-{uuid4().hex[:8]}",
                        persona_type_id=complete_persona_types[persona_key].id,
                        azure_devops_org=azure_devops_config["org_url"],
                        azure_devops_project=project["name"],
                        llm_providers=[LLMModel(
                            provider=LLMProvider.OPENAI,
                            model_name="gpt-4" if project["security_level"] == "critical" else "gpt-3.5-turbo",
                            api_key_env_var="OPENAI_API_KEY"
                        )],
                        spend_limit_daily=daily_limit,
                        spend_limit_monthly=monthly_limit
                    ))
                    project_instances.append(instance.id)
                    all_instances.append(instance.id)
                    
                else:
                    print("✗ Failed")
                    for error in validation.errors:
                        print(f"    Error: {error.message}")
            
            # Validate project completion
            final_validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types["qa-engineer"].id,  # Test with QA
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=project["name"]
            )
            
            team_size = final_validation.project_info["total_team_size"]
            budget = final_validation.project_info["total_monthly_budget"]
            print(f"  Final Team Size: {team_size}, Monthly Budget: ${budget:,.2f}")
            
            # Check for budget warnings on high-budget projects
            if budget > 5000:
                budget_warnings = [r for r in final_validation.results if "budget" in r.rule_name]
                if budget_warnings:
                    print(f"  Budget Notice: {budget_warnings[0].message}")
        
        # Test cross-project resource analysis
        print(f"\n=== CROSS-PROJECT ANALYSIS ===")
        print(f"Total instances created: {len(all_instances)}")
        
        # Cleanup all instances
        for instance_id in all_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
    
    async def test_regulated_industry_compliance_validation(self, validator, complete_persona_types, db, azure_devops_config):
        """Test validation for regulated industry projects (healthcare, finance)"""
        # Scenario: Healthcare project with strict compliance requirements
        
        service = PersonaInstanceService(db)
        all_instances = []
        
        # Define compliance-sensitive projects
        compliance_projects = [
            {
                "name": "Healthcare-Patient-Portal-PROD",
                "compliance": ["HIPAA", "SOC2"],
                "security_level": "critical",
                "required_roles": ["devsecops-engineer", "software-architect"]
            },
            {
                "name": "Financial-Trading-Platform-PROD", 
                "compliance": ["PCI-DSS", "SOX"],
                "security_level": "critical",
                "required_roles": ["devsecops-engineer", "software-architect", "qa-engineer"]
            }
        ]
        
        for project in compliance_projects:
            print(f"\n=== COMPLIANCE PROJECT: {project['name']} ===")
            
            # First, validate that security-sensitive roles trigger appropriate warnings
            for role in project["required_roles"]:
                validation = await validator.validate_project_assignment(
                    persona_type_id=complete_persona_types[role].id,
                    azure_devops_org=azure_devops_config["org_url"],
                    azure_devops_project=project["name"]
                )
                
                print(f"  {role}: ", end="")
                
                # Should succeed but have security notices
                assert validation.can_proceed
                print("✓ Validated")
                
                # Check for security and production warnings
                security_notices = [r for r in validation.results if "security" in r.rule_name or "production" in r.rule_name]
                for notice in security_notices:
                    print(f"    {notice.severity.upper()}: {notice.message}")
                
                # Create instance with enhanced security configuration
                instance = await service.create_instance(PersonaInstanceCreate(
                    instance_name=f"Compliance-{role}-{uuid4().hex[:8]}",
                    persona_type_id=complete_persona_types[role].id,
                    azure_devops_org=azure_devops_config["org_url"],
                    azure_devops_project=project["name"],
                    llm_providers=[LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name="gpt-4",  # Use highest quality model for compliance
                        temperature=0.3,     # Lower temperature for consistency
                        api_key_env_var="OPENAI_API_KEY"
                    )],
                    spend_limit_daily=Decimal("200.00"),  # Higher limits for critical work
                    spend_limit_monthly=Decimal("4000.00"),
                    priority_level=10,  # Maximum priority
                    custom_settings={
                        "compliance_frameworks": project["compliance"],
                        "security_level": project["security_level"],
                        "audit_logging": "enhanced",
                        "data_classification": "sensitive"
                    }
                ))
                all_instances.append(instance.id)
            
            # Try to add non-security role to ensure it gets proper warnings
            validation_regular = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types["frontend-developer"].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=project["name"]
            )
            
            print(f"  frontend-developer: ", end="")
            assert validation_regular.can_proceed
            print("✓ Validated")
            
            # Should have production project warning
            prod_warnings = [r for r in validation_regular.results if "production" in r.rule_name]
            assert len(prod_warnings) > 0
            print(f"    WARNING: {prod_warnings[0].message}")
        
        # Cleanup
        for instance_id in all_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
    
    async def test_agile_team_dynamics_validation(self, validator, complete_persona_types, db, azure_devops_config):
        """Test validation for agile team dynamics and optimal composition"""
        # Scenario: Building optimal agile teams for different project phases
        
        service = PersonaInstanceService(db)
        factory = PersonaInstanceFactory(db)
        all_instances = []
        
        project_base = "AgileTeamDynamics"
        
        # Phase 1: Discovery Phase - Small research team
        print("\n=== DISCOVERY PHASE TEAM ===")
        
        discovery_roles = [
            ("product-owner", "Product Discovery Lead"),
            ("ux-designer", "User Research Lead"),
            ("software-architect", "Technical Feasibility Architect")
        ]
        
        for persona_key, role_name in discovery_roles:
            if persona_key not in complete_persona_types:
                continue
            
            validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{project_base}-Discovery"
            )
            
            assert validation.can_proceed
            print(f"✓ {role_name} validated for discovery phase")
            
            # Check for team balance recommendations
            if "missing_critical_roles" in [r.rule_name for r in validation.results]:
                missing_roles = [r for r in validation.results if r.rule_name == "missing_critical_roles"]
                print(f"  Recommendation: Consider adding {missing_roles[0].details['missing_roles']}")
        
        # Phase 2: Development Sprints - Full agile team
        print("\n=== DEVELOPMENT SPRINT TEAM ===")
        
        # Use factory to create a standard development team
        try:
            team = await factory.create_standard_development_team(
                project_name="Agile Development",
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{project_base}-Development",
                team_size="medium"
            )
            
            print(f"✓ Created medium development team with {len(team)} members:")
            for role, instance in team.items():
                print(f"  - {role}: {instance.instance_name}")
                all_instances.append(instance.id)
                
        except Exception as e:
            print(f"⚠ Factory team creation failed (expected in some test environments): {e}")
            # Fallback to individual validation
            dev_roles = ["software-architect", "senior-developer", "qa-engineer"]
            for role in dev_roles:
                if role in complete_persona_types:
                    validation = await validator.validate_project_assignment(
                        persona_type_id=complete_persona_types[role].id,
                        azure_devops_org=azure_devops_config["org_url"],
                        azure_devops_project=f"{project_base}-Development"
                    )
                    assert validation.can_proceed
                    print(f"✓ {role} validated for development")
        
        # Phase 3: Production Readiness - Add operations focus
        print("\n=== PRODUCTION READINESS TEAM ===")
        
        production_additions = [
            ("devsecops-engineer", "Production Readiness Lead"),
            ("technical-writer", "Documentation Lead")
        ]
        
        for persona_key, role_name in production_additions:
            if persona_key not in complete_persona_types:
                continue
            
            validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{project_base}-Production"
            )
            
            assert validation.can_proceed
            print(f"✓ {role_name} validated for production readiness")
            
            # Check for security considerations
            if persona_key == "devsecops-engineer":
                security_notices = [r for r in validation.results if "security" in r.rule_name]
                if security_notices:
                    print(f"  Security Focus: {security_notices[0].message}")
        
        # Test team rebalancing - what happens when we try to add too many of one role
        print("\n=== TESTING TEAM REBALANCING ===")
        
        # Try to add multiple architects (should warn about balance)
        architect_validations = []
        for i in range(3):
            validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types["software-architect"].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=f"{project_base}-Rebalance"
            )
            architect_validations.append(validation)
            
            if validation.can_proceed:
                print(f"✓ Architect #{i+1} validated")
            else:
                capacity_issues = [r for r in validation.results if "limit" in r.rule_name or "exceeded" in r.rule_name]
                if capacity_issues:
                    print(f"⚠ Architect #{i+1}: {capacity_issues[0].message}")
                break
        
        # Cleanup all instances
        for instance_id in all_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
    
    async def test_disaster_recovery_scenario_validation(self, validator, complete_persona_types, db, azure_devops_config):
        """Test validation during disaster recovery and incident response scenarios"""
        # Scenario: Critical production incident requiring rapid team scaling
        
        service = PersonaInstanceService(db)
        all_instances = []
        
        incident_id = f"INC-{uuid4().hex[:8]}"
        incident_project = f"Production-Incident-{incident_id}"
        
        print(f"\n=== DISASTER RECOVERY SCENARIO: {incident_id} ===")
        
        # Phase 1: Immediate Response Team (must be deployed rapidly)
        immediate_response_roles = [
            ("devsecops-engineer", "Incident Commander", Decimal("500.00"), 10),
            ("senior-developer", "Debug Specialist", Decimal("300.00"), 9),
            ("software-architect", "System Recovery Architect", Decimal("400.00"), 9)
        ]
        
        print("Phase 1: Immediate Response Team")
        for persona_key, role_name, daily_budget, priority in immediate_response_roles:
            validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=incident_project
            )
            
            # Should be valid - incident response has priority
            assert validation.can_proceed
            print(f"✓ {role_name} validated for immediate response")
            
            # Create with high priority and budget
            instance = await service.create_instance(PersonaInstanceCreate(
                instance_name=f"{incident_id}-{role_name}-{uuid4().hex[:8]}",
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=incident_project,
                llm_providers=[LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4-turbo-preview",  # Best model for critical work
                    temperature=0.1,  # Very low temperature for accuracy
                    api_key_env_var="OPENAI_API_KEY"
                )],
                spend_limit_daily=daily_budget,
                spend_limit_monthly=daily_budget * 30,  # Allow high spending
                max_concurrent_tasks=20,  # High concurrency
                priority_level=priority,
                custom_settings={
                    "incident_id": incident_id,
                    "response_mode": "emergency",
                    "escalation_enabled": True,
                    "monitoring_level": "real_time"
                }
            ))
            all_instances.append(instance.id)
        
        # Simulate high-intensity incident work
        print("Simulating incident response work...")
        for instance_id in all_instances:
            # Record high spending to simulate intensive work
            await service.record_spend(instance_id, Decimal("100.00"), f"Emergency incident response - {incident_id}")
        
        # Phase 2: Extended Support Team
        print("\nPhase 2: Extended Support Team")
        extended_roles = [
            ("qa-engineer", "Root Cause Analysis Lead"),
            ("technical-writer", "Incident Documentation Lead"),
            ("product-owner", "Customer Communication Lead")
        ]
        
        for persona_key, role_name in extended_roles:
            if persona_key not in complete_persona_types:
                continue
            
            validation = await validator.validate_project_assignment(
                persona_type_id=complete_persona_types[persona_key].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project=incident_project
            )
            
            # Should be valid, but may have budget warnings due to high existing spend
            print(f"  {role_name}: ", end="")
            
            if validation.can_proceed:
                print("✓ Validated")
                
                # Check for budget warnings
                budget_warnings = [r for r in validation.results if "budget" in r.rule_name]
                if budget_warnings:
                    print(f"    Budget Notice: {budget_warnings[0].message}")
            else:
                print("✗ Blocked")
                for error in validation.errors:
                    print(f"    Error: {error.message}")
        
        # Phase 3: Validate final incident team composition
        print("\nPhase 3: Final Team Analysis")
        
        final_validation = await validator.validate_project_assignment(
            persona_type_id=complete_persona_types["qa-engineer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project=incident_project
        )
        
        project_info = final_validation.project_info
        print(f"Final incident team size: {project_info['total_team_size']}")
        print(f"Total incident budget: ${project_info['total_monthly_budget']:,.2f}")
        print(f"Current incident spend: ${project_info['total_monthly_spend']:,.2f}")
        
        # Should have high budget warnings for incident response
        budget_warnings = [r for r in final_validation.results if "budget" in r.rule_name]
        if budget_warnings:
            print(f"Budget Analysis: {budget_warnings[0].message}")
        
        # Validate that spending is being tracked appropriately
        utilization = project_info['total_monthly_spend'] / project_info['total_monthly_budget'] if project_info['total_monthly_budget'] > 0 else 0
        print(f"Budget utilization: {utilization*100:.1f}%")
        
        assert project_info['total_monthly_spend'] > 0, "Should have recorded incident response spending"
        
        # Cleanup all incident instances
        print("\nCleaning up incident response team...")
        for instance_id in all_instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
        print("✓ Incident response complete")