"""
Project Assignment Validation Service

Validates that persona instances can be properly assigned to Azure DevOps projects
with appropriate permissions, constraints, and business rules.
"""

import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import re

from backend.services.database import DatabaseManager
from backend.models.persona_instance import PersonaInstance
from backend.models.persona_type import PersonaType


class ValidationSeverity(str, Enum):
    """Validation result severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """Single validation result"""
    rule_name: str
    severity: ValidationSeverity
    message: str
    details: Optional[Dict[str, Any]] = None
    can_proceed: bool = True
    suggested_action: Optional[str] = None


@dataclass
class ProjectAssignmentValidation:
    """Complete validation results for project assignment"""
    is_valid: bool
    can_proceed: bool
    results: List[ValidationResult]
    project_info: Dict[str, Any]
    recommendations: List[str]
    
    @property
    def errors(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == ValidationSeverity.ERROR]
    
    @property
    def warnings(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == ValidationSeverity.WARNING]
    
    @property
    def critical_issues(self) -> List[ValidationResult]:
        return [r for r in self.results if r.severity == ValidationSeverity.CRITICAL]


class ProjectAssignmentValidator:
    """
    Validates project assignments for persona instances
    
    Checks:
    1. Azure DevOps project existence and permissions
    2. Project capacity and resource constraints
    3. Persona type compatibility with project requirements
    4. Team composition and RACI conflicts
    5. Spend budget allocation and limits
    6. Security and compliance requirements
    """
    
    # Maximum personas per project by type
    MAX_PERSONAS_PER_PROJECT = {
        "software-architect": 2,
        "senior-developer": 5,
        "backend-developer": 8,
        "frontend-developer": 8,
        "qa-engineer": 4,
        "devsecops-engineer": 2,
        "product-owner": 1,
        "scrum-master": 1,
        "technical-writer": 2,
        "data-scientist": 3
    }
    
    # Required persona types for different project types
    PROJECT_TYPE_REQUIREMENTS = {
        "web-application": [
            "software-architect",
            "frontend-developer", 
            "backend-developer",
            "qa-engineer"
        ],
        "api-service": [
            "software-architect",
            "backend-developer",
            "qa-engineer",
            "devsecops-engineer"
        ],
        "data-platform": [
            "software-architect",
            "data-scientist",
            "backend-developer",
            "devsecops-engineer"
        ],
        "mobile-app": [
            "software-architect",
            "mobile-developer",
            "qa-engineer",
            "ux-designer"
        ]
    }
    
    # Conflicting persona assignments (RACI conflicts)
    RACI_CONFLICTS = {
        ("product-owner", "product-owner"): "Only one Product Owner per project",
        ("scrum-master", "scrum-master"): "Only one Scrum Master per project", 
        ("software-architect", "software-architect"): "Maximum 2 Software Architects per project"
    }
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
    async def validate_project_assignment(
        self,
        persona_type_id: UUID,
        azure_devops_org: str,
        azure_devops_project: str,
        repository_name: Optional[str] = None,
        instance_id: Optional[UUID] = None  # For updates
    ) -> ProjectAssignmentValidation:
        """
        Comprehensive validation of project assignment
        
        Args:
            persona_type_id: ID of persona type to assign
            azure_devops_org: Azure DevOps organization URL
            azure_devops_project: Project name
            repository_name: Optional specific repository
            instance_id: Optional instance ID for updates (excludes self from checks)
            
        Returns:
            ProjectAssignmentValidation with complete results
        """
        results = []
        project_info = {}
        recommendations = []
        
        # Get persona type information
        persona_type = await self._get_persona_type(persona_type_id)
        if not persona_type:
            return ProjectAssignmentValidation(
                is_valid=False,
                can_proceed=False,
                results=[ValidationResult(
                    rule_name="persona_type_exists",
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Persona type {persona_type_id} not found",
                    can_proceed=False
                )],
                project_info={},
                recommendations=["Verify the persona type ID is correct"]
            )
        
        # 1. Validate Azure DevOps project format and accessibility
        org_validation = await self._validate_azure_devops_org(azure_devops_org)
        results.extend(org_validation)
        
        project_validation = await self._validate_azure_devops_project(
            azure_devops_org, azure_devops_project
        )
        results.extend(project_validation)
        
        # 2. Check project capacity constraints
        capacity_validation = await self._validate_project_capacity(
            persona_type, azure_devops_project, instance_id
        )
        results.extend(capacity_validation)
        
        # 3. Validate team composition and RACI
        team_validation = await self._validate_team_composition(
            persona_type, azure_devops_project, instance_id
        )
        results.extend(team_validation)
        
        # 4. Check repository access if specified
        if repository_name:
            repo_validation = await self._validate_repository_access(
                azure_devops_org, azure_devops_project, repository_name
            )
            results.extend(repo_validation)
        
        # 5. Validate spend budget allocation
        budget_validation = await self._validate_budget_allocation(
            persona_type, azure_devops_project
        )
        results.extend(budget_validation)
        
        # 6. Security and compliance checks
        security_validation = await self._validate_security_requirements(
            persona_type, azure_devops_org, azure_devops_project
        )
        results.extend(security_validation)
        
        # 7. Project type compatibility
        compatibility_validation = await self._validate_project_type_compatibility(
            persona_type, azure_devops_project
        )
        results.extend(compatibility_validation)
        
        # Collect project information
        project_info = await self._get_project_info(azure_devops_org, azure_devops_project)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(results, persona_type, project_info)
        
        # Determine overall validation status
        critical_issues = [r for r in results if r.severity == ValidationSeverity.CRITICAL]
        error_issues = [r for r in results if r.severity == ValidationSeverity.ERROR]
        blocking_issues = [r for r in results if not r.can_proceed]
        
        is_valid = len(critical_issues) == 0 and len(error_issues) == 0
        can_proceed = len(blocking_issues) == 0
        
        return ProjectAssignmentValidation(
            is_valid=is_valid,
            can_proceed=can_proceed,
            results=results,
            project_info=project_info,
            recommendations=recommendations
        )
    
    async def _validate_azure_devops_org(self, azure_devops_org: str) -> List[ValidationResult]:
        """Validate Azure DevOps organization URL format and accessibility"""
        results = []
        
        # URL format validation
        if not azure_devops_org:
            results.append(ValidationResult(
                rule_name="org_url_required",
                severity=ValidationSeverity.CRITICAL,
                message="Azure DevOps organization URL is required",
                can_proceed=False,
                suggested_action="Provide a valid Azure DevOps organization URL"
            ))
            return results
        
        # Normalize URL
        if not azure_devops_org.startswith(("http://", "https://")):
            azure_devops_org = f"https://{azure_devops_org}"
        
        # URL pattern validation
        devops_patterns = [
            r"https://dev\.azure\.com/[a-zA-Z0-9\-_]+",
            r"https://[a-zA-Z0-9\-_]+\.visualstudio\.com"
        ]
        
        if not any(re.match(pattern, azure_devops_org) for pattern in devops_patterns):
            results.append(ValidationResult(
                rule_name="org_url_format",
                severity=ValidationSeverity.ERROR,
                message="Invalid Azure DevOps organization URL format",
                details={"provided_url": azure_devops_org},
                can_proceed=False,
                suggested_action="Use format: https://dev.azure.com/yourorg or https://yourorg.visualstudio.com"
            ))
        
        # TODO: In real implementation, test actual connectivity
        # For now, assume accessibility based on URL format
        results.append(ValidationResult(
            rule_name="org_accessibility",
            severity=ValidationSeverity.INFO,
            message="Azure DevOps organization URL appears valid",
            details={"org_url": azure_devops_org}
        ))
        
        return results
    
    async def _validate_azure_devops_project(
        self, 
        azure_devops_org: str, 
        azure_devops_project: str
    ) -> List[ValidationResult]:
        """Validate Azure DevOps project name and existence"""
        results = []
        
        if not azure_devops_project:
            results.append(ValidationResult(
                rule_name="project_name_required",
                severity=ValidationSeverity.CRITICAL,
                message="Azure DevOps project name is required",
                can_proceed=False
            ))
            return results
        
        # Project name format validation
        if len(azure_devops_project) > 64:
            results.append(ValidationResult(
                rule_name="project_name_length",
                severity=ValidationSeverity.ERROR,
                message="Project name exceeds maximum length of 64 characters",
                details={"name_length": len(azure_devops_project)},
                can_proceed=False
            ))
        
        # Valid characters check
        if not re.match(r"^[a-zA-Z0-9\-_ ]+$", azure_devops_project):
            results.append(ValidationResult(
                rule_name="project_name_characters",
                severity=ValidationSeverity.ERROR,
                message="Project name contains invalid characters",
                details={"project_name": azure_devops_project},
                can_proceed=False,
                suggested_action="Use only letters, numbers, hyphens, underscores, and spaces"
            ))
        
        # Check if this is our test project
        if azure_devops_project == "AI-Personas-Test-Sandbox-2":
            results.append(ValidationResult(
                rule_name="test_project_access",
                severity=ValidationSeverity.INFO,
                message="Using designated test project",
                details={"project_name": azure_devops_project}
            ))
        else:
            # For non-test projects, add warning about validation
            results.append(ValidationResult(
                rule_name="project_existence_check",
                severity=ValidationSeverity.WARNING,
                message="Cannot verify project existence without API credentials",
                details={"project_name": azure_devops_project},
                suggested_action="Ensure project exists and you have access"
            ))
        
        return results
    
    async def _validate_project_capacity(
        self,
        persona_type: PersonaType,
        azure_devops_project: str,
        instance_id: Optional[UUID] = None
    ) -> List[ValidationResult]:
        """Validate project capacity constraints"""
        results = []
        
        # Get current personas in project
        query = """
        SELECT 
            pt.type_name,
            COUNT(*) as count
        FROM orchestrator.persona_instances pi
        JOIN orchestrator.persona_types pt ON pi.persona_type_id = pt.id
        WHERE pi.azure_devops_project = $1
        AND pi.is_active = true
        """
        
        params = [azure_devops_project]
        
        # Exclude current instance if updating
        if instance_id:
            query += " AND pi.id != $2"
            params.append(instance_id)
        
        query += " GROUP BY pt.type_name"
        
        current_counts = await self.db.execute_query(query, *params)
        count_by_type = {row['type_name']: row['count'] for row in current_counts}
        
        # Check against limits
        current_count = count_by_type.get(persona_type.type_name, 0)
        max_allowed = self.MAX_PERSONAS_PER_PROJECT.get(persona_type.type_name, 10)
        
        if current_count >= max_allowed:
            results.append(ValidationResult(
                rule_name="max_personas_exceeded",
                severity=ValidationSeverity.ERROR,
                message=f"Maximum {persona_type.type_name} instances ({max_allowed}) already in project",
                details={
                    "current_count": current_count,
                    "max_allowed": max_allowed,
                    "persona_type": persona_type.type_name
                },
                can_proceed=False,
                suggested_action=f"Deactivate existing {persona_type.type_name} or increase project limits"
            ))
        elif current_count >= max_allowed * 0.8:  # 80% warning threshold
            results.append(ValidationResult(
                rule_name="approaching_persona_limit",
                severity=ValidationSeverity.WARNING,
                message=f"Approaching limit for {persona_type.type_name} instances in project",
                details={
                    "current_count": current_count,
                    "max_allowed": max_allowed,
                    "percentage_used": (current_count / max_allowed) * 100
                }
            ))
        
        # Check total project size
        total_personas = sum(count_by_type.values())
        if total_personas >= 20:  # Arbitrary large project limit
            results.append(ValidationResult(
                rule_name="large_project_warning",
                severity=ValidationSeverity.WARNING,
                message=f"Project has {total_personas} active personas (large team)",
                details={"total_personas": total_personas},
                suggested_action="Consider project splitting or resource optimization"
            ))
        
        return results
    
    async def _validate_team_composition(
        self,
        persona_type: PersonaType,
        azure_devops_project: str,
        instance_id: Optional[UUID] = None
    ) -> List[ValidationResult]:
        """Validate team composition and RACI conflicts"""
        results = []
        
        # Get existing team composition
        query = """
        SELECT 
            pt.type_name,
            pt.display_name,
            COUNT(*) as count,
            ARRAY_AGG(pi.instance_name) as instance_names
        FROM orchestrator.persona_instances pi
        JOIN orchestrator.persona_types pt ON pi.persona_type_id = pt.id
        WHERE pi.azure_devops_project = $1
        AND pi.is_active = true
        """
        
        params = [azure_devops_project]
        
        if instance_id:
            query += " AND pi.id != $2"
            params.append(instance_id)
        
        query += " GROUP BY pt.type_name, pt.display_name"
        
        team_composition = await self.db.execute_query(query, *params)
        
        # Check for RACI conflicts
        for member in team_composition:
            conflict_key = (member['type_name'], persona_type.type_name)
            reverse_key = (persona_type.type_name, member['type_name'])
            
            if conflict_key in self.RACI_CONFLICTS:
                results.append(ValidationResult(
                    rule_name="raci_conflict",
                    severity=ValidationSeverity.ERROR,
                    message=self.RACI_CONFLICTS[conflict_key],
                    details={
                        "existing_type": member['type_name'],
                        "new_type": persona_type.type_name,
                        "existing_instances": member['instance_names']
                    },
                    can_proceed=False,
                    suggested_action="Deactivate existing conflicting instances or choose different persona type"
                ))
            elif reverse_key in self.RACI_CONFLICTS:
                results.append(ValidationResult(
                    rule_name="raci_conflict",
                    severity=ValidationSeverity.ERROR,
                    message=self.RACI_CONFLICTS[reverse_key],
                    details={
                        "existing_type": member['type_name'],
                        "new_type": persona_type.type_name,
                        "existing_instances": member['instance_names']
                    },
                    can_proceed=False,
                    suggested_action="Deactivate existing conflicting instances or choose different persona type"
                ))
        
        # Check for recommended team balance
        if len(team_composition) == 0:
            results.append(ValidationResult(
                rule_name="first_team_member",
                severity=ValidationSeverity.INFO,
                message="This will be the first persona in the project",
                details={"persona_type": persona_type.type_name}
            ))
        
        # Suggest missing critical roles
        existing_types = {member['type_name'] for member in team_composition}
        existing_types.add(persona_type.type_name)  # Include the one being added
        
        critical_missing = []
        if "software-architect" not in existing_types and len(team_composition) >= 2:
            critical_missing.append("software-architect")
        if "qa-engineer" not in existing_types and len(team_composition) >= 3:
            critical_missing.append("qa-engineer")
        
        if critical_missing:
            results.append(ValidationResult(
                rule_name="missing_critical_roles",
                severity=ValidationSeverity.WARNING,
                message=f"Consider adding critical roles: {', '.join(critical_missing)}",
                details={"missing_roles": critical_missing},
                suggested_action="Add recommended persona types for complete team"
            ))
        
        return results
    
    async def _validate_repository_access(
        self,
        azure_devops_org: str,
        azure_devops_project: str,
        repository_name: str
    ) -> List[ValidationResult]:
        """Validate repository access and naming"""
        results = []
        
        if not repository_name:
            return results
        
        # Repository name validation
        if len(repository_name) > 64:
            results.append(ValidationResult(
                rule_name="repo_name_length",
                severity=ValidationSeverity.ERROR,
                message="Repository name exceeds maximum length of 64 characters",
                details={"name_length": len(repository_name)},
                can_proceed=False
            ))
        
        # Valid characters
        if not re.match(r"^[a-zA-Z0-9\-_.]+$", repository_name):
            results.append(ValidationResult(
                rule_name="repo_name_characters",
                severity=ValidationSeverity.ERROR,
                message="Repository name contains invalid characters",
                details={"repository_name": repository_name},
                can_proceed=False,
                suggested_action="Use only letters, numbers, hyphens, underscores, and periods"
            ))
        
        # TODO: In real implementation, verify repository exists and access
        results.append(ValidationResult(
            rule_name="repo_access_check",
            severity=ValidationSeverity.WARNING,
            message="Cannot verify repository access without API credentials",
            details={"repository_name": repository_name},
            suggested_action="Ensure repository exists and persona has appropriate access"
        ))
        
        return results
    
    async def _validate_budget_allocation(
        self,
        persona_type: PersonaType,
        azure_devops_project: str
    ) -> List[ValidationResult]:
        """Validate spend budget allocation for project"""
        results = []
        
        # Get current project spend allocation
        query = """
        SELECT 
            SUM(spend_limit_daily) as total_daily_budget,
            SUM(spend_limit_monthly) as total_monthly_budget,
            SUM(current_spend_daily) as total_daily_spend,
            SUM(current_spend_monthly) as total_monthly_spend,
            COUNT(*) as active_instances
        FROM orchestrator.persona_instances
        WHERE azure_devops_project = $1
        AND is_active = true
        """
        
        budget_info = await self.db.execute_query(query, azure_devops_project, fetch_one=True)
        
        if budget_info and budget_info['total_monthly_budget']:
            total_monthly_budget = float(budget_info['total_monthly_budget'])
            
            # Warn if project budget is getting large
            if total_monthly_budget > 10000:  # $10k/month
                results.append(ValidationResult(
                    rule_name="high_project_budget",
                    severity=ValidationSeverity.WARNING,
                    message=f"Project monthly budget is ${total_monthly_budget:,.2f}",
                    details={
                        "monthly_budget": total_monthly_budget,
                        "active_instances": budget_info['active_instances']
                    },
                    suggested_action="Review budget allocation and consider optimization"
                ))
            
            # Check budget utilization
            if budget_info['total_monthly_spend']:
                utilization = float(budget_info['total_monthly_spend']) / total_monthly_budget
                if utilization > 0.9:
                    results.append(ValidationResult(
                        rule_name="high_budget_utilization",
                        severity=ValidationSeverity.WARNING,
                        message=f"Project budget utilization at {utilization*100:.1f}%",
                        details={
                            "utilization_percentage": utilization * 100,
                            "monthly_spend": float(budget_info['total_monthly_spend']),
                            "monthly_budget": total_monthly_budget
                        },
                        suggested_action="Monitor spend closely or increase budget"
                    ))
        
        return results
    
    async def _validate_security_requirements(
        self,
        persona_type: PersonaType,
        azure_devops_org: str,
        azure_devops_project: str
    ) -> List[ValidationResult]:
        """Validate security and compliance requirements"""
        results = []
        
        # Security-sensitive persona types
        security_sensitive_types = {
            "devsecops-engineer",
            "software-architect", 
            "security-architect",
            "data-scientist"
        }
        
        if persona_type.type_name in security_sensitive_types:
            results.append(ValidationResult(
                rule_name="security_sensitive_role",
                severity=ValidationSeverity.INFO,
                message=f"Assigning security-sensitive role: {persona_type.display_name}",
                details={"persona_type": persona_type.type_name},
                suggested_action="Ensure appropriate security controls and monitoring"
            ))
        
        # Project name-based security checks
        if any(keyword in azure_devops_project.lower() for keyword in ['prod', 'production', 'live']):
            results.append(ValidationResult(
                rule_name="production_project_warning",
                severity=ValidationSeverity.WARNING,
                message="Assigning persona to production project",
                details={"project_name": azure_devops_project},
                suggested_action="Ensure enhanced monitoring and approval processes"
            ))
        
        return results
    
    async def _validate_project_type_compatibility(
        self,
        persona_type: PersonaType,
        azure_devops_project: str
    ) -> List[ValidationResult]:
        """Validate persona type compatibility with inferred project type"""
        results = []
        
        # Infer project type from name/existing team
        project_type = await self._infer_project_type(azure_devops_project)
        
        if project_type:
            required_types = self.PROJECT_TYPE_REQUIREMENTS.get(project_type, [])
            if required_types and persona_type.type_name not in required_types:
                results.append(ValidationResult(
                    rule_name="project_type_compatibility",
                    severity=ValidationSeverity.WARNING,
                    message=f"Persona type may not be optimal for {project_type} project",
                    details={
                        "project_type": project_type,
                        "persona_type": persona_type.type_name,
                        "recommended_types": required_types
                    },
                    suggested_action=f"Consider using: {', '.join(required_types)}"
                ))
        
        return results
    
    async def _get_persona_type(self, persona_type_id: UUID) -> Optional[PersonaType]:
        """Get persona type by ID"""
        query = """
        SELECT id, type_name, display_name, category, description, 
               base_workflow_id, capabilities, default_llm_config
        FROM orchestrator.persona_types
        WHERE id = $1
        """
        
        result = await self.db.execute_query(query, persona_type_id, fetch_one=True)
        if not result:
            return None
        
        return PersonaType(
            id=result['id'],
            type_name=result['type_name'],
            display_name=result['display_name'],
            category=result['category'],
            description=result['description'],
            base_workflow_id=result['base_workflow_id'],
            capabilities=result['capabilities'],
            default_llm_config=result['default_llm_config']
        )
    
    async def _get_project_info(
        self,
        azure_devops_org: str,
        azure_devops_project: str
    ) -> Dict[str, Any]:
        """Get comprehensive project information"""
        info = {
            "organization": azure_devops_org,
            "project_name": azure_devops_project,
            "validation_timestamp": datetime.utcnow().isoformat()
        }
        
        # Get team composition
        query = """
        SELECT 
            pt.type_name,
            pt.display_name,
            COUNT(*) as count,
            SUM(pi.spend_limit_monthly) as total_budget,
            SUM(pi.current_spend_monthly) as total_spend
        FROM orchestrator.persona_instances pi
        JOIN orchestrator.persona_types pt ON pi.persona_type_id = pt.id
        WHERE pi.azure_devops_project = $1
        AND pi.is_active = true
        GROUP BY pt.type_name, pt.display_name
        """
        
        team_data = await self.db.execute_query(query, azure_devops_project)
        
        info["team_composition"] = [
            {
                "type_name": row['type_name'],
                "display_name": row['display_name'],
                "count": row['count'],
                "monthly_budget": float(row['total_budget'] or 0),
                "monthly_spend": float(row['total_spend'] or 0)
            }
            for row in team_data
        ]
        
        info["total_team_size"] = sum(row['count'] for row in team_data)
        info["total_monthly_budget"] = sum(row['monthly_budget'] for row in info["team_composition"])
        info["total_monthly_spend"] = sum(row['monthly_spend'] for row in info["team_composition"])
        
        return info
    
    async def _infer_project_type(self, azure_devops_project: str) -> Optional[str]:
        """Infer project type from name and existing team composition"""
        project_lower = azure_devops_project.lower()
        
        # Name-based inference
        if any(keyword in project_lower for keyword in ['api', 'service', 'backend']):
            return "api-service"
        elif any(keyword in project_lower for keyword in ['web', 'app', 'frontend', 'ui']):
            return "web-application"
        elif any(keyword in project_lower for keyword in ['data', 'analytics', 'ml', 'ai']):
            return "data-platform"
        elif any(keyword in project_lower for keyword in ['mobile', 'ios', 'android']):
            return "mobile-app"
        
        # TODO: Team composition-based inference could be added here
        
        return None
    
    def _generate_recommendations(
        self,
        results: List[ValidationResult],
        persona_type: PersonaType,
        project_info: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable recommendations based on validation results"""
        recommendations = []
        
        # Collect all suggested actions
        for result in results:
            if result.suggested_action:
                recommendations.append(result.suggested_action)
        
        # Add general recommendations
        if project_info.get("total_team_size", 0) == 0:
            recommendations.append("Consider starting with core roles: Software Architect, Senior Developer, QA Engineer")
        
        team_size = project_info.get("total_team_size", 0)
        if team_size > 10:
            recommendations.append("Large team detected - consider splitting into smaller focused teams")
        
        monthly_budget = project_info.get("total_monthly_budget", 0)
        if monthly_budget > 5000:
            recommendations.append("High monthly budget - implement cost monitoring and optimization")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)
        
        return unique_recommendations