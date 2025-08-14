"""
Service layer for PersonaInstance management
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from backend.models.persona_instance import (
    PersonaInstance,
    PersonaInstanceCreate,
    PersonaInstanceUpdate,
    PersonaInstanceResponse
)
from backend.repositories.persona_instance_repository import PersonaInstanceRepository
from backend.services.database import DatabaseManager


class PersonaInstanceService:
    """Service for managing persona instances with business logic"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.repository = PersonaInstanceRepository(db_manager)
        self.db = db_manager
    
    async def create_instance(self, data: PersonaInstanceCreate) -> PersonaInstanceResponse:
        """Create a new persona instance with validation"""
        # Check if instance name already exists for this project
        existing = await self.repository.get_by_name_and_project(
            data.instance_name,
            data.azure_devops_project
        )
        if existing:
            raise ValueError(
                f"Instance '{data.instance_name}' already exists in project '{data.azure_devops_project}'"
            )
        
        # Validate persona type exists
        persona_type = await self._validate_persona_type_exists(data.persona_type_id)
        if not persona_type:
            raise ValueError(f"Persona type with ID '{data.persona_type_id}' does not exist")
        
        # Create the instance
        instance = await self.repository.create(data)
        
        # Return as response model
        return await self._to_response(instance)
    
    async def get_instance(self, instance_id: UUID) -> Optional[PersonaInstanceResponse]:
        """Get a persona instance by ID"""
        instance = await self.repository.get_by_id(instance_id)
        return await self._to_response(instance) if instance else None
    
    async def list_instances(
        self,
        persona_type_id: Optional[UUID] = None,
        project: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PersonaInstanceResponse]:
        """List persona instances with optional filtering"""
        instances = await self.repository.list_all(
            persona_type_id=persona_type_id,
            project=project,
            is_active=is_active,
            limit=limit,
            offset=offset
        )
        return [await self._to_response(i) for i in instances]
    
    async def update_instance(
        self,
        instance_id: UUID,
        data: PersonaInstanceUpdate
    ) -> Optional[PersonaInstanceResponse]:
        """Update a persona instance"""
        # If updating instance name, check for duplicates
        if data.instance_name:
            current = await self.repository.get_by_id(instance_id)
            if current:
                existing = await self.repository.get_by_name_and_project(
                    data.instance_name,
                    current.azure_devops_project
                )
                if existing and existing.id != instance_id:
                    raise ValueError(
                        f"Instance name '{data.instance_name}' already exists in this project"
                    )
        
        instance = await self.repository.update(instance_id, data)
        return await self._to_response(instance) if instance else None
    
    async def deactivate_instance(self, instance_id: UUID) -> bool:
        """Deactivate a persona instance"""
        # Check if instance has active tasks
        task_count = await self.repository.count_active_tasks(instance_id)
        if task_count > 0:
            raise ValueError(
                f"Cannot deactivate instance with {task_count} active tasks"
            )
        
        return await self.repository.deactivate(instance_id)
    
    async def record_spend(
        self,
        instance_id: UUID,
        amount: Decimal,
        operation: str
    ) -> bool:
        """Record spend for an instance"""
        # Check if spend would exceed limits
        limits = await self.repository.check_spend_limits(instance_id)
        
        # Update both daily and monthly
        success = await self.repository.update_spend(
            instance_id,
            amount,  # daily
            amount   # monthly
        )
        
        # Check if limits exceeded after update
        new_limits = await self.repository.check_spend_limits(instance_id)
        if new_limits['daily_exceeded'] or new_limits['monthly_exceeded']:
            # Log warning or send notification
            instance = await self.repository.get_by_id(instance_id)
            if instance:
                print(f"WARNING: Instance {instance.instance_name} has exceeded spend limits")
        
        return success
    
    async def get_instances_by_type(
        self,
        persona_type_id: UUID
    ) -> List[PersonaInstanceResponse]:
        """Get all active instances of a specific persona type"""
        instances = await self.repository.get_active_instances_by_type(persona_type_id)
        return [await self._to_response(i) for i in instances]
    
    async def find_available_instance(
        self,
        persona_type_id: UUID,
        project: Optional[str] = None
    ) -> Optional[PersonaInstanceResponse]:
        """Find an available instance of a persona type for a project"""
        instances = await self.repository.get_active_instances_by_type(persona_type_id)
        
        # Filter by project if specified
        if project:
            instances = [i for i in instances if i.azure_devops_project == project]
        
        # Find instance with available capacity
        for instance in instances:
            response = await self._to_response(instance)
            if response.available_capacity > 0:
                # Check spend limits
                limits = await self.repository.check_spend_limits(instance.id)
                if not limits['daily_exceeded'] and not limits['monthly_exceeded']:
                    return response
        
        return None
    
    async def get_instance_statistics(self) -> Dict[str, Any]:
        """Get statistics about persona instances"""
        all_instances = await self.repository.list_all()
        
        stats = {
            "total_instances": len(all_instances),
            "active_instances": len([i for i in all_instances if i.is_active]),
            "by_type": {},
            "by_project": {},
            "total_daily_spend": Decimal("0.00"),
            "total_monthly_spend": Decimal("0.00")
        }
        
        for instance in all_instances:
            # Count by type
            type_name = instance.persona_type_name or "Unknown"
            if type_name not in stats["by_type"]:
                stats["by_type"][type_name] = 0
            stats["by_type"][type_name] += 1
            
            # Count by project
            project = instance.azure_devops_project
            if project not in stats["by_project"]:
                stats["by_project"][project] = 0
            stats["by_project"][project] += 1
            
            # Sum spend
            stats["total_daily_spend"] += instance.current_spend_daily
            stats["total_monthly_spend"] += instance.current_spend_monthly
        
        return stats
    
    async def reset_daily_spend_all(self) -> int:
        """Reset daily spend for all instances (scheduled job)"""
        return await self.repository.reset_daily_spend()
    
    async def reset_monthly_spend_all(self) -> int:
        """Reset monthly spend for all instances (scheduled job)"""
        return await self.repository.reset_monthly_spend()
    
    async def _validate_persona_type_exists(self, persona_type_id: UUID) -> bool:
        """Check if a persona type exists"""
        query = """
        SELECT EXISTS(
            SELECT 1 FROM orchestrator.persona_types
            WHERE id = $1
        )
        """
        result = await self.db.execute_query(query, persona_type_id, fetch_one=True)
        return result['exists'] if result else False
    
    async def _to_response(self, instance: PersonaInstance) -> PersonaInstanceResponse:
        """Convert PersonaInstance to PersonaInstanceResponse with computed fields"""
        # If we don't have persona type info, fetch it
        if not instance.persona_type_name:
            instance = await self.repository.get_by_id(instance.id)
        
        # Get current task count
        task_count = await self.repository.count_active_tasks(instance.id)
        
        response = PersonaInstanceResponse(
            **instance.model_dump(),
            current_task_count=task_count
        )
        
        # Calculate percentages and capacity
        response.calculate_spend_percentages()
        response.calculate_capacity()
        
        return response