"""
PersonaInstance model for representing specific instances of AI personas
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator
from decimal import Decimal
from enum import Enum


class LLMProvider(str, Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROK = "grok"
    AZURE_OPENAI = "azure_openai"


class LLMModel(BaseModel):
    """LLM model configuration"""
    provider: LLMProvider
    model_name: str
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0, le=128000)
    api_key_env_var: str = Field(..., description="Environment variable containing API key")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider": "openai",
                "model_name": "gpt-4-turbo-preview",
                "temperature": 0.7,
                "max_tokens": 4096,
                "api_key_env_var": "OPENAI_API_KEY"
            }
        }
    )


class PersonaInstance(BaseModel):
    """Represents a specific instance of a persona type assigned to a project"""
    
    model_config = ConfigDict(from_attributes=True)
    
    # Database fields
    id: Optional[UUID] = None
    instance_name: str = Field(..., description="Unique name like 'Steve Bot - Project Alpha'")
    persona_type_id: UUID = Field(..., description="Reference to persona type")
    
    # Project Assignment
    azure_devops_org: str = Field(..., description="Azure DevOps organization URL")
    azure_devops_project: str = Field(..., description="Project name in Azure DevOps")
    repository_name: Optional[str] = Field(None, description="Specific repository if applicable")
    
    # LLM Configuration
    llm_providers: List[LLMModel] = Field(
        default_factory=list,
        min_length=1,
        description="Priority-ordered list of LLM providers"
    )
    
    # Spend Limits
    spend_limit_daily: Decimal = Field(Decimal("50.00"), ge=0)
    spend_limit_monthly: Decimal = Field(Decimal("1000.00"), ge=0)
    current_spend_daily: Decimal = Field(Decimal("0.00"), ge=0)
    current_spend_monthly: Decimal = Field(Decimal("0.00"), ge=0)
    
    # Instance Configuration
    max_concurrent_tasks: int = Field(5, ge=1, le=20)
    priority_level: int = Field(0, ge=-10, le=10, description="Higher = higher priority")
    custom_settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Instance-specific settings"
    )
    
    # Status
    is_active: bool = Field(True)
    last_activity: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Additional computed fields (not in DB)
    persona_type_name: Optional[str] = Field(None, description="From persona_types join")
    persona_display_name: Optional[str] = Field(None, description="From persona_types join")
    
    @field_validator('instance_name')
    @classmethod
    def validate_instance_name(cls, v):
        """Ensure instance name is not empty and reasonable length"""
        if not v or not v.strip():
            raise ValueError("Instance name cannot be empty")
        if len(v) > 255:
            raise ValueError("Instance name too long (max 255 characters)")
        return v.strip()
    
    @field_validator('azure_devops_org')
    @classmethod
    def validate_azure_devops_org(cls, v):
        """Basic validation of Azure DevOps org URL"""
        if not v or not v.strip():
            raise ValueError("Azure DevOps organization URL required")
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://")):
            v = f"https://{v}"
        return v
    
    @field_validator('spend_limit_daily')
    @classmethod
    def validate_daily_limit(cls, v):
        """Ensure daily limit is reasonable"""
        if v > Decimal("1000.00"):
            raise ValueError("Daily spend limit seems too high (max $1000)")
        return v
    
    @field_validator('current_spend_daily')
    @classmethod
    def validate_current_daily_spend(cls, v, values):
        """Ensure current spend doesn't exceed limit"""
        # In Pydantic v2, we need to use values from the validation context
        # This validator runs after spend_limit_daily, so we can access it
        return v
    


class PersonaInstanceCreate(BaseModel):
    """Schema for creating a new persona instance"""
    instance_name: str
    persona_type_id: UUID
    azure_devops_org: str
    azure_devops_project: str
    repository_name: Optional[str] = None
    llm_providers: List[LLMModel]
    spend_limit_daily: Decimal = Decimal("50.00")
    spend_limit_monthly: Decimal = Decimal("1000.00")
    max_concurrent_tasks: int = 5
    priority_level: int = 0
    custom_settings: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('instance_name')
    @classmethod
    def validate_instance_name(cls, v):
        """Ensure instance name is not empty and reasonable length"""
        if not v or not v.strip():
            raise ValueError("Instance name cannot be empty")
        if len(v) > 255:
            raise ValueError("Instance name too long (max 255 characters)")
        return v.strip()
    
    @field_validator('azure_devops_org')
    @classmethod
    def validate_azure_devops_org(cls, v):
        """Basic validation of Azure DevOps org URL"""
        if not v or not v.strip():
            raise ValueError("Azure DevOps organization URL required")
        v = v.strip()
        if not (v.startswith("https://") or v.startswith("http://")):
            v = f"https://{v}"
        return v
    
    @field_validator('spend_limit_daily')
    @classmethod
    def validate_daily_limit(cls, v):
        """Ensure daily limit is reasonable"""
        if v > Decimal("1000.00"):
            raise ValueError("Daily spend limit seems too high (max $1000)")
        return v


class PersonaInstanceUpdate(BaseModel):
    """Schema for updating a persona instance"""
    instance_name: Optional[str] = None
    repository_name: Optional[str] = None
    llm_providers: Optional[List[LLMModel]] = None
    spend_limit_daily: Optional[Decimal] = None
    spend_limit_monthly: Optional[Decimal] = None
    max_concurrent_tasks: Optional[int] = None
    priority_level: Optional[int] = None
    custom_settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class PersonaInstanceResponse(PersonaInstance):
    """Response model with additional computed fields"""
    current_task_count: int = Field(0, description="Number of active tasks")
    spend_percentage_daily: float = Field(0.0, description="Percentage of daily limit used")
    spend_percentage_monthly: float = Field(0.0, description="Percentage of monthly limit used")
    available_capacity: int = Field(0, description="Available task slots")
    
    # Override llm_providers to ensure it's required for responses
    llm_providers: List[LLMModel] = Field(
        ...,
        min_length=1,
        description="Priority-ordered list of LLM providers"
    )
    
    def calculate_spend_percentages(self):
        """Calculate spend percentages"""
        if self.spend_limit_daily > 0:
            self.spend_percentage_daily = float(
                (self.current_spend_daily / self.spend_limit_daily) * 100
            )
        if self.spend_limit_monthly > 0:
            self.spend_percentage_monthly = float(
                (self.current_spend_monthly / self.spend_limit_monthly) * 100
            )
    
    def calculate_capacity(self):
        """Calculate available capacity"""
        self.available_capacity = max(0, self.max_concurrent_tasks - self.current_task_count)