"""
PersonaType model for representing different types of AI personas
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class PersonaCategory(str, Enum):
    """Categories for grouping persona types"""
    DEVELOPMENT = "development"
    QUALITY = "quality"
    ARCHITECTURE = "architecture"
    OPERATIONS = "operations"
    MANAGEMENT = "management"
    SPECIALIZED = "specialized"
    TESTING = "testing"


class PersonaType(BaseModel):
    """Represents a type of persona (e.g., Software Architect, QA Engineer)"""
    
    model_config = ConfigDict(from_attributes=True)
    
    # Database fields
    id: Optional[UUID] = None
    type_name: str = Field(..., description="Unique identifier like 'software-architect'")
    display_name: str = Field(..., description="Human-readable name like 'Software Architect'")
    base_workflow_id: Optional[str] = Field(None, description="Reference to persona workflow")
    default_capabilities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Default capabilities and permissions for this persona type"
    )
    created_at: Optional[datetime] = None
    
    # Additional fields for the model
    category: PersonaCategory = Field(..., description="Category for grouping")
    description: Optional[str] = Field(None, description="Description of the persona's role")
    required_skills: list[str] = Field(
        default_factory=list,
        description="Skills required for this persona type"
    )
    compatible_workflows: list[str] = Field(
        default_factory=list,
        description="List of workflow IDs this persona can execute"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type_name": "software-architect",
                "display_name": "Software Architect",
                "category": "architecture",
                "description": "Designs software systems and makes architectural decisions",
                "base_workflow_id": "persona-software-architect",
                "default_capabilities": {
                    "can_create_design_docs": True,
                    "can_review_code": True,
                    "can_make_architectural_decisions": True,
                    "max_concurrent_tasks": 5
                },
                "required_skills": [
                    "system_design",
                    "code_review",
                    "technical_documentation",
                    "decision_making"
                ],
                "compatible_workflows": [
                    "wf0-feature-development",
                    "wf5-pull-request-creation",
                    "wf6-pull-request-review"
                ]
            }
        }
    )


class PersonaTypeCreate(BaseModel):
    """Schema for creating a new persona type"""
    type_name: str
    display_name: str
    category: PersonaCategory
    description: Optional[str] = None
    base_workflow_id: Optional[str] = None
    default_capabilities: Dict[str, Any] = Field(default_factory=dict)
    required_skills: list[str] = Field(default_factory=list)
    compatible_workflows: list[str] = Field(default_factory=list)


class PersonaTypeUpdate(BaseModel):
    """Schema for updating a persona type"""
    display_name: Optional[str] = None
    category: Optional[PersonaCategory] = None
    description: Optional[str] = None
    base_workflow_id: Optional[str] = None
    default_capabilities: Optional[Dict[str, Any]] = None
    required_skills: Optional[list[str]] = None
    compatible_workflows: Optional[list[str]] = None


class PersonaTypeResponse(PersonaType):
    """Response model with additional computed fields"""
    instance_count: int = Field(0, description="Number of active instances of this type")
    is_available: bool = Field(True, description="Whether new instances can be created")