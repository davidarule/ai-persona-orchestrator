"""
Factory for creating and configuring PersonaInstance objects
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from decimal import Decimal

from backend.models.persona_instance import (
    PersonaInstance,
    PersonaInstanceCreate,
    LLMProvider,
    LLMModel
)
from backend.models.persona_type import PersonaType
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.persona_instance_service import PersonaInstanceService
from backend.services.database import DatabaseManager


class PersonaInstanceFactory:
    """Factory for creating persona instances with standard configurations"""
    
    # Default LLM configurations by persona category
    DEFAULT_LLM_CONFIGS = {
        "architecture": [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4-turbo-preview",
                temperature=0.7,
                max_tokens=4096,
                api_key_env_var="OPENAI_API_KEY"
            ),
            LLMModel(
                provider=LLMProvider.ANTHROPIC,
                model_name="claude-3-opus-20240229",
                temperature=0.5,
                api_key_env_var="ANTHROPIC_API_KEY"
            )
        ],
        "development": [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                temperature=0.7,
                max_tokens=4096,
                api_key_env_var="OPENAI_API_KEY"
            )
        ],
        "testing": [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                temperature=0.5,
                max_tokens=2048,
                api_key_env_var="OPENAI_API_KEY"
            )
        ],
        "operations": [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                temperature=0.3,
                max_tokens=2048,
                api_key_env_var="OPENAI_API_KEY"
            )
        ],
        "management": [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                temperature=0.7,
                max_tokens=4096,
                api_key_env_var="OPENAI_API_KEY"
            )
        ]
    }
    
    # Default spend limits by persona category
    DEFAULT_SPEND_LIMITS = {
        "architecture": {"daily": Decimal("100.00"), "monthly": Decimal("2000.00")},
        "development": {"daily": Decimal("75.00"), "monthly": Decimal("1500.00")},
        "testing": {"daily": Decimal("50.00"), "monthly": Decimal("1000.00")},
        "operations": {"daily": Decimal("75.00"), "monthly": Decimal("1500.00")},
        "management": {"daily": Decimal("50.00"), "monthly": Decimal("1000.00")},
        "specialized": {"daily": Decimal("100.00"), "monthly": Decimal("2000.00")}
    }
    
    # Default settings by persona type
    PERSONA_SETTINGS = {
        "software-architect": {
            "code_style": "clean_architecture",
            "documentation_level": "comprehensive",
            "review_thoroughness": "high",
            "preferred_patterns": ["SOLID", "DDD", "CQRS"],
            "communication_style": "technical"
        },
        "backend-developer": {
            "preferred_languages": ["Python", "Java", "C#", "Go"],
            "testing_approach": "TDD",
            "code_style": "clean_code",
            "documentation_level": "moderate"
        },
        "frontend-developer": {
            "preferred_frameworks": ["React", "Vue", "Angular"],
            "styling_approach": "component-based",
            "testing_approach": "component_testing",
            "accessibility_focus": "high"
        },
        "qa-engineer": {
            "testing_types": ["unit", "integration", "e2e", "performance"],
            "automation_preference": "high",
            "bug_reporting_detail": "comprehensive",
            "test_coverage_target": 80
        },
        "devsecops-engineer": {
            "security_scanning": "continuous",
            "compliance_frameworks": ["SOC2", "ISO27001", "GDPR"],
            "automation_level": "maximum",
            "monitoring_approach": "proactive"
        },
        "product-owner": {
            "communication_style": "business-focused",
            "prioritization_method": "value-driven",
            "stakeholder_engagement": "high",
            "documentation_preference": "user-stories"
        }
    }
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.service = PersonaInstanceService(db_manager)
        self.type_repo = PersonaTypeRepository(db_manager)
    
    async def create_instance(
        self,
        instance_name: str,
        persona_type_id: UUID,
        azure_devops_org: str,
        azure_devops_project: str,
        repository_name: Optional[str] = None,
        custom_llm_providers: Optional[List[LLMModel]] = None,
        custom_spend_limits: Optional[Dict[str, Decimal]] = None,
        custom_settings: Optional[Dict[str, Any]] = None,
        max_concurrent_tasks: int = 5,
        priority_level: int = 0
    ) -> PersonaInstance:
        """
        Create a persona instance with smart defaults based on persona type
        
        Args:
            instance_name: Unique name for the instance
            persona_type_id: ID of the persona type
            azure_devops_org: Azure DevOps organization URL
            azure_devops_project: Project name
            repository_name: Optional repository name
            custom_llm_providers: Override default LLM providers
            custom_spend_limits: Override default spend limits
            custom_settings: Additional or override settings
            max_concurrent_tasks: Maximum concurrent tasks
            priority_level: Priority level (-10 to 10)
            
        Returns:
            Created PersonaInstance
        """
        # Get persona type to determine defaults
        persona_type = await self.type_repo.get_by_id(persona_type_id)
        if not persona_type:
            raise ValueError(f"Persona type {persona_type_id} not found")
        
        # Determine LLM providers
        if custom_llm_providers:
            llm_providers = custom_llm_providers
        else:
            category = persona_type.category.value if hasattr(persona_type.category, 'value') else persona_type.category
            llm_providers = self.DEFAULT_LLM_CONFIGS.get(
                category,
                self.DEFAULT_LLM_CONFIGS["development"]
            )
        
        # Determine spend limits
        if custom_spend_limits:
            spend_limit_daily = custom_spend_limits.get("daily", Decimal("50.00"))
            spend_limit_monthly = custom_spend_limits.get("monthly", Decimal("1000.00"))
        else:
            category = persona_type.category.value if hasattr(persona_type.category, 'value') else persona_type.category
            limits = self.DEFAULT_SPEND_LIMITS.get(
                category,
                {"daily": Decimal("50.00"), "monthly": Decimal("1000.00")}
            )
            spend_limit_daily = limits["daily"]
            spend_limit_monthly = limits["monthly"]
        
        # Build settings
        settings = {}
        
        # Add default settings based on persona type
        default_settings = self.PERSONA_SETTINGS.get(persona_type.type_name, {})
        settings.update(default_settings)
        
        # Add category-specific settings
        settings["persona_category"] = persona_type.category.value if hasattr(persona_type.category, 'value') else persona_type.category
        settings["base_workflow_id"] = persona_type.base_workflow_id
        
        # Add/override with custom settings
        if custom_settings:
            settings.update(custom_settings)
        
        # Create the instance
        create_data = PersonaInstanceCreate(
            instance_name=instance_name,
            persona_type_id=persona_type_id,
            azure_devops_org=azure_devops_org,
            azure_devops_project=azure_devops_project,
            repository_name=repository_name,
            llm_providers=llm_providers,
            spend_limit_daily=spend_limit_daily,
            spend_limit_monthly=spend_limit_monthly,
            max_concurrent_tasks=max_concurrent_tasks,
            priority_level=priority_level,
            custom_settings=settings
        )
        
        return await self.service.create_instance(create_data)
    
    async def create_team_instances(
        self,
        project_name: str,
        azure_devops_org: str,
        azure_devops_project: str,
        team_config: Dict[str, Dict[str, Any]]
    ) -> Dict[str, PersonaInstance]:
        """
        Create a complete team of persona instances for a project
        
        Args:
            project_name: Name to use in instance naming
            azure_devops_org: Azure DevOps organization URL
            azure_devops_project: Project name
            team_config: Configuration for each team member
                Example: {
                    "architect": {
                        "persona_type_name": "software-architect",
                        "repository": "architecture-docs",
                        "priority": 10
                    },
                    "backend_lead": {
                        "persona_type_name": "backend-developer",
                        "repository": "backend-api",
                        "priority": 8
                    }
                }
                
        Returns:
            Dictionary mapping role names to created instances
        """
        instances = {}
        
        for role_name, config in team_config.items():
            # Get persona type by name
            persona_type_name = config.get("persona_type_name")
            if not persona_type_name:
                raise ValueError(f"persona_type_name required for role {role_name}")
            
            persona_type = await self.type_repo.get_by_name(persona_type_name)
            if not persona_type:
                raise ValueError(f"Persona type '{persona_type_name}' not found")
            
            # Create instance name
            instance_name = f"{role_name.replace('_', ' ').title()} - {project_name}"
            
            # Create the instance
            instance = await self.create_instance(
                instance_name=instance_name,
                persona_type_id=persona_type.id,
                azure_devops_org=azure_devops_org,
                azure_devops_project=azure_devops_project,
                repository_name=config.get("repository"),
                custom_llm_providers=config.get("llm_providers"),
                custom_spend_limits=config.get("spend_limits"),
                custom_settings=config.get("settings"),
                max_concurrent_tasks=config.get("max_tasks", 5),
                priority_level=config.get("priority", 0)
            )
            
            instances[role_name] = instance
        
        return instances
    
    async def create_standard_development_team(
        self,
        project_name: str,
        azure_devops_org: str,
        azure_devops_project: str,
        team_size: str = "medium"
    ) -> Dict[str, PersonaInstance]:
        """
        Create a standard development team based on project size
        
        Args:
            project_name: Name to use in instance naming
            azure_devops_org: Azure DevOps organization URL
            azure_devops_project: Project name
            team_size: "small", "medium", or "large"
            
        Returns:
            Dictionary mapping role names to created instances
        """
        # Define team compositions - using display names as fallback
        team_compositions = {
            "small": {
                "lead_developer": {
                    "persona_type_name": "senior-developer",
                    "persona_display_name": "Senior Developer",
                    "priority": 8,
                    "max_tasks": 8
                },
                "qa_engineer": {
                    "persona_type_name": "qa-engineer",
                    "persona_display_name": "QA Engineer",
                    "priority": 5,
                    "max_tasks": 5
                }
            },
            "medium": {
                "architect": {
                    "persona_type_name": "software-architect",
                    "priority": 10,
                    "max_tasks": 5
                },
                "backend_lead": {
                    "persona_type_name": "backend-developer",
                    "priority": 8,
                    "max_tasks": 8
                },
                "frontend_lead": {
                    "persona_type_name": "frontend-developer",
                    "priority": 8,
                    "max_tasks": 8
                },
                "qa_lead": {
                    "persona_type_name": "qa-engineer",
                    "priority": 7,
                    "max_tasks": 6
                },
                "devops_engineer": {
                    "persona_type_name": "devsecops-engineer",
                    "priority": 6,
                    "max_tasks": 5
                }
            },
            "large": {
                "chief_architect": {
                    "persona_type_name": "software-architect",
                    "priority": 10,
                    "max_tasks": 5,
                    "spend_limits": {"daily": Decimal("150.00"), "monthly": Decimal("3000.00")}
                },
                "backend_team_lead": {
                    "persona_type_name": "backend-developer",
                    "priority": 9,
                    "max_tasks": 10
                },
                "frontend_team_lead": {
                    "persona_type_name": "frontend-developer",
                    "priority": 9,
                    "max_tasks": 10
                },
                "qa_manager": {
                    "persona_type_name": "qa-engineer",
                    "priority": 8,
                    "max_tasks": 8
                },
                "devops_lead": {
                    "persona_type_name": "devsecops-engineer",
                    "priority": 8,
                    "max_tasks": 8
                },
                "product_owner": {
                    "persona_type_name": "product-owner",
                    "priority": 9,
                    "max_tasks": 5
                },
                "technical_writer": {
                    "persona_type_name": "technical-writer",
                    "priority": 5,
                    "max_tasks": 3
                }
            }
        }
        
        team_config = team_compositions.get(team_size, team_compositions["medium"])
        return await self.create_team_instances(
            project_name=project_name,
            azure_devops_org=azure_devops_org,
            azure_devops_project=azure_devops_project,
            team_config=team_config
        )
    
    async def clone_instance(
        self,
        source_instance_id: UUID,
        new_instance_name: str,
        new_project: Optional[str] = None,
        new_repository: Optional[str] = None
    ) -> PersonaInstance:
        """
        Clone an existing persona instance with a new name and optionally new project
        
        Args:
            source_instance_id: ID of instance to clone
            new_instance_name: Name for the new instance
            new_project: Optional new project (uses source project if not provided)
            new_repository: Optional new repository (uses source if not provided)
            
        Returns:
            Newly created PersonaInstance
        """
        # Get source instance
        source = await self.service.get_instance(source_instance_id)
        if not source:
            raise ValueError(f"Source instance {source_instance_id} not found")
        
        # Create clone
        return await self.create_instance(
            instance_name=new_instance_name,
            persona_type_id=source.persona_type_id,
            azure_devops_org=source.azure_devops_org,
            azure_devops_project=new_project or source.azure_devops_project,
            repository_name=new_repository or source.repository_name,
            custom_llm_providers=source.llm_providers,
            custom_spend_limits={
                "daily": source.spend_limit_daily,
                "monthly": source.spend_limit_monthly
            },
            custom_settings=source.custom_settings,
            max_concurrent_tasks=source.max_concurrent_tasks,
            priority_level=source.priority_level
        )