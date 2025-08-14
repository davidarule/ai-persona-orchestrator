"""
Service layer for PersonaType management
"""

from typing import List, Optional, Dict, Any
from uuid import UUID

from backend.models.persona_type import (
    PersonaType,
    PersonaTypeCreate,
    PersonaTypeUpdate,
    PersonaTypeResponse,
    PersonaCategory
)
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.database import DatabaseManager


class PersonaTypeService:
    """Service for managing persona types with business logic"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.repository = PersonaTypeRepository(db_manager)
        self.db = db_manager
    
    async def create_persona_type(self, data: PersonaTypeCreate) -> PersonaTypeResponse:
        """Create a new persona type with validation"""
        # Check if type_name already exists
        existing = await self.repository.get_by_type_name(data.type_name)
        if existing:
            raise ValueError(f"Persona type '{data.type_name}' already exists")
        
        # Validate workflow ID if provided
        if data.base_workflow_id:
            workflow_exists = await self._validate_workflow_exists(data.base_workflow_id)
            if not workflow_exists:
                raise ValueError(f"Workflow '{data.base_workflow_id}' does not exist")
        
        # Create the persona type
        persona = await self.repository.create(data)
        
        # Return as response model
        return await self._to_response(persona)
    
    async def get_persona_type(self, persona_id: UUID) -> Optional[PersonaTypeResponse]:
        """Get a persona type by ID"""
        persona = await self.repository.get_by_id(persona_id)
        return await self._to_response(persona) if persona else None
    
    async def get_persona_type_by_name(self, type_name: str) -> Optional[PersonaTypeResponse]:
        """Get a persona type by type name"""
        persona = await self.repository.get_by_type_name(type_name)
        return await self._to_response(persona) if persona else None
    
    async def list_persona_types(
        self,
        category: Optional[PersonaCategory] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PersonaTypeResponse]:
        """List all persona types with optional filtering"""
        personas = await self.repository.list_all(category, limit, offset)
        return [await self._to_response(p) for p in personas]
    
    async def update_persona_type(
        self,
        persona_id: UUID,
        data: PersonaTypeUpdate
    ) -> Optional[PersonaTypeResponse]:
        """Update a persona type"""
        # Validate workflow ID if being updated
        if data.base_workflow_id is not None:
            workflow_exists = await self._validate_workflow_exists(data.base_workflow_id)
            if not workflow_exists:
                raise ValueError(f"Workflow '{data.base_workflow_id}' does not exist")
        
        persona = await self.repository.update(persona_id, data)
        return await self._to_response(persona) if persona else None
    
    async def delete_persona_type(self, persona_id: UUID) -> bool:
        """Delete a persona type (only if no active instances)"""
        return await self.repository.delete(persona_id)
    
    async def get_available_persona_types(self) -> List[PersonaTypeResponse]:
        """Get all persona types that can have new instances created"""
        all_types = await self.repository.list_all()
        available = []
        
        for persona_type in all_types:
            response = await self._to_response(persona_type)
            # Check if type is available (could add more logic here)
            if response.is_available:
                available.append(response)
        
        return available
    
    async def get_persona_type_statistics(self) -> Dict[str, Any]:
        """Get statistics about persona types"""
        all_types = await self.repository.list_all()
        
        stats = {
            "total_types": len(all_types),
            "by_category": {},
            "total_instances": 0,
            "most_used": None,
            "least_used": None
        }
        
        # Count by category
        for persona in all_types:
            category = persona.category
            if category not in stats["by_category"]:
                stats["by_category"][category] = 0
            stats["by_category"][category] += 1
        
        # Find most and least used
        max_instances = 0
        min_instances = float('inf')
        
        for persona in all_types:
            count = await self.repository.count_instances(persona.id)
            stats["total_instances"] += count
            
            if count > max_instances:
                max_instances = count
                stats["most_used"] = {
                    "type_name": persona.type_name,
                    "display_name": persona.display_name,
                    "instances": count
                }
            
            if count < min_instances:
                min_instances = count
                stats["least_used"] = {
                    "type_name": persona.type_name,
                    "display_name": persona.display_name,
                    "instances": count
                }
        
        return stats
    
    async def initialize_default_persona_types(self) -> List[PersonaTypeResponse]:
        """Initialize all 25 default persona types from the spec"""
        default_types = self._get_default_persona_types()
        created = await self.repository.bulk_create(default_types)
        return [await self._to_response(p) for p in created]
    
    async def _validate_workflow_exists(self, workflow_id: str) -> bool:
        """Check if a workflow exists in the database"""
        query = """
        SELECT EXISTS(
            SELECT 1 FROM orchestrator.workflow_definitions 
            WHERE name = $1
        )
        """
        result = await self.db.execute_query(query, workflow_id, fetch_one=True)
        return result['exists'] if result else False
    
    async def _to_response(self, persona: PersonaType) -> PersonaTypeResponse:
        """Convert PersonaType to PersonaTypeResponse with computed fields"""
        instance_count = await self.repository.count_instances(persona.id)
        
        # Determine availability (can be enhanced with more logic)
        is_available = True
        max_instances = persona.default_capabilities.get('max_instances', 100)
        if instance_count >= max_instances:
            is_available = False
        
        return PersonaTypeResponse(
            **persona.model_dump(),
            instance_count=instance_count,
            is_available=is_available
        )
    
    def _get_default_persona_types(self) -> List[PersonaTypeCreate]:
        """Get the 25 default persona types"""
        return [
            # Development Team
            PersonaTypeCreate(
                type_name="senior-developer",
                display_name="Senior Developer",
                category=PersonaCategory.DEVELOPMENT,
                description="Experienced developer who writes high-quality code and mentors others",
                base_workflow_id="persona-senior-developer",
                default_capabilities={
                    "can_write_code": True,
                    "can_review_code": True,
                    "can_mentor": True,
                    "max_concurrent_tasks": 8
                },
                required_skills=["coding", "code_review", "mentoring", "architecture"],
                compatible_workflows=["wf0", "wf1", "wf4", "wf5", "wf6", "wf7", "wf8"]
            ),
            PersonaTypeCreate(
                type_name="backend-developer",
                display_name="Backend Developer",
                category=PersonaCategory.DEVELOPMENT,
                description="Specializes in server-side development and APIs",
                base_workflow_id="persona-backend-developer",
                default_capabilities={
                    "can_write_backend_code": True,
                    "can_design_apis": True,
                    "can_optimize_performance": True,
                    "max_concurrent_tasks": 6
                },
                required_skills=["backend_development", "api_design", "databases", "performance"],
                compatible_workflows=["wf0", "wf1", "wf4", "wf5"]
            ),
            PersonaTypeCreate(
                type_name="frontend-developer",
                display_name="Frontend Developer",
                category=PersonaCategory.DEVELOPMENT,
                description="Specializes in user interface and user experience implementation",
                base_workflow_id="persona-frontend-developer",
                default_capabilities={
                    "can_write_frontend_code": True,
                    "can_implement_ui": True,
                    "can_optimize_ux": True,
                    "max_concurrent_tasks": 6
                },
                required_skills=["frontend_development", "ui_implementation", "css", "javascript"],
                compatible_workflows=["wf0", "wf1", "wf4", "wf5"]
            ),
            PersonaTypeCreate(
                type_name="mobile-developer",
                display_name="Mobile Developer",
                category=PersonaCategory.DEVELOPMENT,
                description="Develops mobile applications for iOS and Android",
                base_workflow_id="persona-mobile-developer",
                default_capabilities={
                    "can_develop_mobile": True,
                    "can_optimize_mobile": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["mobile_development", "ios", "android", "react_native"],
                compatible_workflows=["wf0", "wf1", "wf4", "wf5"]
            ),
            PersonaTypeCreate(
                type_name="ai-engineer",
                display_name="AI Engineer",
                category=PersonaCategory.DEVELOPMENT,
                description="Specializes in AI/ML implementations and integrations",
                base_workflow_id="persona-ai-engineer",
                default_capabilities={
                    "can_implement_ai": True,
                    "can_train_models": True,
                    "can_optimize_ml": True,
                    "max_concurrent_tasks": 4
                },
                required_skills=["machine_learning", "ai_development", "model_training", "data_science"],
                compatible_workflows=["wf0", "wf1", "wf4", "wf5"]
            ),
            
            # Quality & Testing
            PersonaTypeCreate(
                type_name="qa-test-engineer",
                display_name="QA Test Engineer",
                category=PersonaCategory.QUALITY,
                description="Creates and executes comprehensive test plans",
                base_workflow_id="persona-qa-test-engineer",
                default_capabilities={
                    "can_write_tests": True,
                    "can_execute_tests": True,
                    "can_automate_tests": True,
                    "max_concurrent_tasks": 6
                },
                required_skills=["test_planning", "test_automation", "quality_assurance", "bug_tracking"],
                compatible_workflows=["wf0", "wf1", "wf2", "wf6", "wf13"]
            ),
            PersonaTypeCreate(
                type_name="software-qa",
                display_name="Software QA",
                category=PersonaCategory.QUALITY,
                description="Ensures software quality through manual and automated testing",
                base_workflow_id="persona-software-qa",
                default_capabilities={
                    "can_test_software": True,
                    "can_write_test_cases": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["quality_assurance", "test_cases", "regression_testing"],
                compatible_workflows=["wf0", "wf1", "wf2", "wf6"]
            ),
            PersonaTypeCreate(
                type_name="test-engineer",
                display_name="Test Engineer",
                category=PersonaCategory.QUALITY,
                description="Focuses on test automation and continuous testing",
                base_workflow_id="persona-test-engineer",
                default_capabilities={
                    "can_automate_tests": True,
                    "can_integrate_ci": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["test_automation", "ci_integration", "performance_testing"],
                compatible_workflows=["wf0", "wf1", "wf2", "wf13", "wf14"]
            ),
            PersonaTypeCreate(
                type_name="integration-engineer",
                display_name="Integration Engineer",
                category=PersonaCategory.QUALITY,
                description="Ensures system components work together seamlessly",
                base_workflow_id="persona-integration-engineer",
                default_capabilities={
                    "can_test_integration": True,
                    "can_design_integration": True,
                    "max_concurrent_tasks": 4
                },
                required_skills=["integration_testing", "api_testing", "system_integration"],
                compatible_workflows=["wf0", "wf1", "wf14"]
            ),
            
            # Architecture & Design
            PersonaTypeCreate(
                type_name="software-architect",
                display_name="Software Architect",
                category=PersonaCategory.ARCHITECTURE,
                description="Designs software systems and makes architectural decisions",
                base_workflow_id="persona-software-architect",
                default_capabilities={
                    "can_create_design_docs": True,
                    "can_review_code": True,
                    "can_make_architectural_decisions": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["system_design", "code_review", "technical_documentation", "decision_making"],
                compatible_workflows=["wf0", "wf5", "wf6", "wf16", "wf17"]
            ),
            PersonaTypeCreate(
                type_name="systems-architect",
                display_name="Systems Architect",
                category=PersonaCategory.ARCHITECTURE,
                description="Designs large-scale distributed systems",
                base_workflow_id="persona-systems-architect",
                default_capabilities={
                    "can_design_systems": True,
                    "can_plan_infrastructure": True,
                    "max_concurrent_tasks": 4
                },
                required_skills=["distributed_systems", "infrastructure_design", "scalability"],
                compatible_workflows=["wf0", "wf15", "wf17"]
            ),
            PersonaTypeCreate(
                type_name="security-architect",
                display_name="Security Architect",
                category=PersonaCategory.ARCHITECTURE,
                description="Designs secure systems and security protocols",
                base_workflow_id="persona-security-architect",
                default_capabilities={
                    "can_design_security": True,
                    "can_audit_security": True,
                    "max_concurrent_tasks": 4
                },
                required_skills=["security_design", "threat_modeling", "security_protocols"],
                compatible_workflows=["wf0", "wf2", "wf6", "wf11"]
            ),
            PersonaTypeCreate(
                type_name="ui-ux-designer",
                display_name="UI/UX Designer",
                category=PersonaCategory.ARCHITECTURE,
                description="Designs user interfaces and experiences",
                base_workflow_id="persona-ui-ux-designer",
                default_capabilities={
                    "can_design_ui": True,
                    "can_create_prototypes": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["ui_design", "ux_design", "prototyping", "user_research"],
                compatible_workflows=["wf0", "wf4", "wf5"]
            ),
            
            # Operations & Infrastructure
            PersonaTypeCreate(
                type_name="devsecops-engineer",
                display_name="DevSecOps Engineer",
                category=PersonaCategory.OPERATIONS,
                description="Integrates security into DevOps practices",
                base_workflow_id="persona-devsecops-engineer",
                default_capabilities={
                    "can_manage_ci_cd": True,
                    "can_implement_security": True,
                    "can_automate_deployment": True,
                    "max_concurrent_tasks": 6
                },
                required_skills=["ci_cd", "security_automation", "infrastructure_as_code", "monitoring"],
                compatible_workflows=["wf0", "wf2", "wf9", "wf11", "wf14"]
            ),
            PersonaTypeCreate(
                type_name="site-reliability-engineer",
                display_name="Site Reliability Engineer",
                category=PersonaCategory.OPERATIONS,
                description="Ensures system reliability and uptime",
                base_workflow_id="persona-site-reliability-engineer",
                default_capabilities={
                    "can_monitor_systems": True,
                    "can_handle_incidents": True,
                    "can_improve_reliability": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["monitoring", "incident_response", "reliability_engineering", "automation"],
                compatible_workflows=["wf2", "wf9", "wf11", "wf14"]
            ),
            PersonaTypeCreate(
                type_name="cloud-engineer",
                display_name="Cloud Engineer",
                category=PersonaCategory.OPERATIONS,
                description="Manages cloud infrastructure and services",
                base_workflow_id="persona-cloud-engineer",
                default_capabilities={
                    "can_manage_cloud": True,
                    "can_optimize_costs": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["cloud_platforms", "infrastructure_management", "cost_optimization"],
                compatible_workflows=["wf0", "wf15"]
            ),
            PersonaTypeCreate(
                type_name="configuration-release-engineer",
                display_name="Configuration Release Engineer",
                category=PersonaCategory.OPERATIONS,
                description="Manages configuration and release processes",
                base_workflow_id="persona-configuration-release-engineer",
                default_capabilities={
                    "can_manage_releases": True,
                    "can_configure_systems": True,
                    "max_concurrent_tasks": 4
                },
                required_skills=["release_management", "configuration_management", "deployment"],
                compatible_workflows=["wf0", "wf2", "wf8", "wf11", "wf15"]
            ),
            
            # Management & Analysis
            PersonaTypeCreate(
                type_name="engineering-manager",
                display_name="Engineering Manager",
                category=PersonaCategory.MANAGEMENT,
                description="Manages engineering teams and projects",
                base_workflow_id="persona-engineering-manager",
                default_capabilities={
                    "can_manage_teams": True,
                    "can_make_decisions": True,
                    "can_approve_changes": True,
                    "max_concurrent_tasks": 8
                },
                required_skills=["team_management", "project_management", "decision_making", "leadership"],
                compatible_workflows=["wf0", "wf2", "wf5", "wf6", "wf8", "wf11", "wf12", "wf16"]
            ),
            PersonaTypeCreate(
                type_name="product-owner",
                display_name="Product Owner",
                category=PersonaCategory.MANAGEMENT,
                description="Defines product vision and priorities",
                base_workflow_id="persona-product-owner",
                default_capabilities={
                    "can_define_requirements": True,
                    "can_prioritize_features": True,
                    "can_approve_features": True,
                    "max_concurrent_tasks": 6
                },
                required_skills=["product_management", "requirements_gathering", "prioritization", "stakeholder_management"],
                compatible_workflows=["wf0", "wf12", "wf16"]
            ),
            PersonaTypeCreate(
                type_name="scrum-master",
                display_name="Scrum Master",
                category=PersonaCategory.MANAGEMENT,
                description="Facilitates agile processes and removes blockers",
                base_workflow_id="persona-scrum-master",
                default_capabilities={
                    "can_facilitate_agile": True,
                    "can_remove_blockers": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["agile_methodology", "facilitation", "team_coordination"],
                compatible_workflows=["wf0", "wf12"]
            ),
            PersonaTypeCreate(
                type_name="business-analyst",
                display_name="Business Analyst",
                category=PersonaCategory.MANAGEMENT,
                description="Analyzes business needs and requirements",
                base_workflow_id="persona-business-analyst",
                default_capabilities={
                    "can_analyze_requirements": True,
                    "can_create_specifications": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["business_analysis", "requirements_analysis", "documentation"],
                compatible_workflows=["wf0", "wf12"]
            ),
            PersonaTypeCreate(
                type_name="requirements-analyst",
                display_name="Requirements Analyst",
                category=PersonaCategory.MANAGEMENT,
                description="Gathers and documents detailed requirements",
                base_workflow_id="persona-requirements-analyst",
                default_capabilities={
                    "can_gather_requirements": True,
                    "can_document_requirements": True,
                    "max_concurrent_tasks": 4
                },
                required_skills=["requirements_gathering", "documentation", "analysis"],
                compatible_workflows=["wf0", "wf12"]
            ),
            
            # Specialized Roles
            PersonaTypeCreate(
                type_name="security-engineer",
                display_name="Security Engineer",
                category=PersonaCategory.SPECIALIZED,
                description="Implements security measures and protocols",
                base_workflow_id="persona-security-engineer",
                default_capabilities={
                    "can_implement_security": True,
                    "can_audit_code": True,
                    "can_fix_vulnerabilities": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["security_implementation", "vulnerability_assessment", "security_tools"],
                compatible_workflows=["wf0", "wf1", "wf2", "wf6", "wf11"]
            ),
            PersonaTypeCreate(
                type_name="data-engineer-dba",
                display_name="Data Engineer/DBA",
                category=PersonaCategory.SPECIALIZED,
                description="Manages databases and data pipelines",
                base_workflow_id="persona-data-engineer-dba",
                default_capabilities={
                    "can_manage_databases": True,
                    "can_optimize_queries": True,
                    "can_design_data_pipelines": True,
                    "max_concurrent_tasks": 5
                },
                required_skills=["database_management", "data_engineering", "sql", "performance_tuning"],
                compatible_workflows=["wf0", "wf1", "wf14"]
            ),
            PersonaTypeCreate(
                type_name="technical-writer",
                display_name="Technical Writer",
                category=PersonaCategory.SPECIALIZED,
                description="Creates technical documentation and guides",
                base_workflow_id="persona-technical-writer",
                default_capabilities={
                    "can_write_documentation": True,
                    "can_create_guides": True,
                    "max_concurrent_tasks": 4
                },
                required_skills=["technical_writing", "documentation", "communication"],
                compatible_workflows=["wf0", "wf4", "wf12"]
            ),
        ]