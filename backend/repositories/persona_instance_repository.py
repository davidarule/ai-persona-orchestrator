"""
Repository for PersonaInstance database operations
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
import asyncpg
from datetime import datetime
import json
from decimal import Decimal

from backend.models.persona_instance import (
    PersonaInstance,
    PersonaInstanceCreate,
    PersonaInstanceUpdate,
    LLMModel
)
from backend.services.database import DatabaseManager
from backend.utils.db_utils import QueryBuilder


class PersonaInstanceRepository:
    """Repository for managing PersonaInstance entities in the database"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.schema = "orchestrator"
        self.table = "persona_instances"
    
    async def create(self, instance: PersonaInstanceCreate) -> PersonaInstance:
        """Create a new persona instance"""
        query = f"""
        INSERT INTO {self.schema}.{self.table} (
            instance_name, persona_type_id, azure_devops_org, 
            azure_devops_project, repository_name, llm_providers,
            spend_limit_daily, spend_limit_monthly,
            max_concurrent_tasks, priority_level, custom_settings
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        RETURNING *
        """
        
        # Convert LLM providers to JSON
        llm_providers_json = json.dumps([
            provider.model_dump() for provider in instance.llm_providers
        ])
        
        values = [
            instance.instance_name,
            instance.persona_type_id,
            instance.azure_devops_org,
            instance.azure_devops_project,
            instance.repository_name,
            llm_providers_json,
            instance.spend_limit_daily,
            instance.spend_limit_monthly,
            instance.max_concurrent_tasks,
            instance.priority_level,
            json.dumps(instance.custom_settings)
        ]
        
        row = await self.db.execute_query(query, *values, fetch_one=True)
        
        if row:
            return self._row_to_model(row)
        
        raise ValueError("Failed to create persona instance")
    
    async def get_by_id(self, instance_id: UUID) -> Optional[PersonaInstance]:
        """Get a persona instance by ID with type information"""
        query = f"""
        SELECT 
            pi.*,
            pt.type_name as persona_type_name,
            pt.display_name as persona_display_name
        FROM {self.schema}.{self.table} pi
        JOIN {self.schema}.persona_types pt ON pi.persona_type_id = pt.id
        WHERE pi.id = $1
        """
        row = await self.db.execute_query(query, instance_id, fetch_one=True)
        return self._row_to_model(row) if row else None
    
    async def get_by_name_and_project(
        self, 
        instance_name: str, 
        project: str
    ) -> Optional[PersonaInstance]:
        """Get a persona instance by name and project"""
        query = f"""
        SELECT 
            pi.*,
            pt.type_name as persona_type_name,
            pt.display_name as persona_display_name
        FROM {self.schema}.{self.table} pi
        JOIN {self.schema}.persona_types pt ON pi.persona_type_id = pt.id
        WHERE pi.instance_name = $1 AND pi.azure_devops_project = $2
        """
        row = await self.db.execute_query(query, instance_name, project, fetch_one=True)
        return self._row_to_model(row) if row else None
    
    async def list_all(
        self,
        persona_type_id: Optional[UUID] = None,
        project: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PersonaInstance]:
        """List all persona instances with optional filtering"""
        query_parts = [f"""
        SELECT 
            pi.*,
            pt.type_name as persona_type_name,
            pt.display_name as persona_display_name
        FROM {self.schema}.{self.table} pi
        JOIN {self.schema}.persona_types pt ON pi.persona_type_id = pt.id
        """]
        
        where_clauses = []
        params = []
        param_count = 1
        
        if persona_type_id:
            where_clauses.append(f"pi.persona_type_id = ${param_count}")
            params.append(persona_type_id)
            param_count += 1
        
        if project:
            where_clauses.append(f"pi.azure_devops_project = ${param_count}")
            params.append(project)
            param_count += 1
        
        if is_active is not None:
            where_clauses.append(f"pi.is_active = ${param_count}")
            params.append(is_active)
            param_count += 1
        
        if where_clauses:
            query_parts.append("WHERE " + " AND ".join(where_clauses))
        
        query_parts.append("ORDER BY pi.created_at DESC")
        query_parts.append(f"LIMIT ${param_count} OFFSET ${param_count + 1}")
        params.extend([limit, offset])
        
        query = " ".join(query_parts)
        rows = await self.db.execute_query(query, *params)
        
        return [self._row_to_model(row) for row in rows]
    
    async def update(
        self,
        instance_id: UUID,
        update_data: PersonaInstanceUpdate
    ) -> Optional[PersonaInstance]:
        """Update a persona instance"""
        # Get current instance
        current = await self.get_by_id(instance_id)
        if not current:
            return None
        
        # Build update fields
        updates = {}
        
        if update_data.instance_name is not None:
            updates['instance_name'] = update_data.instance_name
        
        if update_data.repository_name is not None:
            updates['repository_name'] = update_data.repository_name
        
        if update_data.llm_providers is not None:
            updates['llm_providers'] = json.dumps([
                provider.model_dump() for provider in update_data.llm_providers
            ])
        
        if update_data.spend_limit_daily is not None:
            updates['spend_limit_daily'] = update_data.spend_limit_daily
        
        if update_data.spend_limit_monthly is not None:
            updates['spend_limit_monthly'] = update_data.spend_limit_monthly
        
        if update_data.max_concurrent_tasks is not None:
            updates['max_concurrent_tasks'] = update_data.max_concurrent_tasks
        
        if update_data.priority_level is not None:
            updates['priority_level'] = update_data.priority_level
        
        if update_data.custom_settings is not None:
            updates['custom_settings'] = json.dumps(update_data.custom_settings)
        
        if update_data.is_active is not None:
            updates['is_active'] = update_data.is_active
        
        if not updates:
            return current
        
        # Execute update - QueryBuilder.update returns a tuple (query, params)
        query, params = QueryBuilder.update(
            self.table,
            updates,
            {"id": instance_id},
            schema=self.schema
        )
        
        # Get updated row with joins
        query = query.replace("RETURNING *", f"""
        RETURNING 
            {self.table}.*,
            (SELECT type_name FROM {self.schema}.persona_types WHERE id = persona_type_id) as persona_type_name,
            (SELECT display_name FROM {self.schema}.persona_types WHERE id = persona_type_id) as persona_display_name
        """)
        
        row = await self.db.execute_query(query, *params, fetch_one=True)
        return self._row_to_model(row) if row else None
    
    async def update_spend(
        self,
        instance_id: UUID,
        daily_amount: Decimal,
        monthly_amount: Decimal
    ) -> bool:
        """Update spend amounts for an instance"""
        query = f"""
        UPDATE {self.schema}.{self.table}
        SET 
            current_spend_daily = current_spend_daily + $1,
            current_spend_monthly = current_spend_monthly + $2,
            last_activity = NOW()
        WHERE id = $3
        """
        
        result = await self.db.execute_query(
            query, 
            daily_amount, 
            monthly_amount, 
            instance_id
        )
        return result is not None
    
    async def reset_daily_spend(self) -> int:
        """Reset daily spend for all instances (called by cron job)"""
        query = f"""
        WITH updated AS (
            UPDATE {self.schema}.{self.table}
            SET current_spend_daily = 0
            WHERE current_spend_daily > 0
            RETURNING id
        )
        SELECT COUNT(*) as count FROM updated
        """
        
        result = await self.db.execute_query(query, fetch_one=True)
        return result['count'] if result else 0
    
    async def reset_monthly_spend(self) -> int:
        """Reset monthly spend for all instances (called by cron job)"""
        query = f"""
        WITH updated AS (
            UPDATE {self.schema}.{self.table}
            SET current_spend_monthly = 0
            WHERE current_spend_monthly > 0
            RETURNING id
        )
        SELECT COUNT(*) as count FROM updated
        """
        
        result = await self.db.execute_query(query, fetch_one=True)
        return result['count'] if result else 0
    
    async def deactivate(self, instance_id: UUID) -> bool:
        """Deactivate a persona instance (soft delete)"""
        query = f"""
        UPDATE {self.schema}.{self.table}
        SET is_active = false
        WHERE id = $1
        """
        
        result = await self.db.execute_query(query, instance_id)
        return result is not None
    
    async def get_active_instances_by_type(
        self, 
        persona_type_id: UUID
    ) -> List[PersonaInstance]:
        """Get all active instances of a specific persona type"""
        return await self.list_all(
            persona_type_id=persona_type_id,
            is_active=True
        )
    
    async def count_active_tasks(self, instance_id: UUID) -> int:
        """Count active tasks for an instance (placeholder for future)"""
        # This will query workflow_executions table in the future
        # For now, return 0
        return 0
    
    async def check_spend_limits(self, instance_id: UUID) -> Dict[str, bool]:
        """Check if instance has exceeded spend limits"""
        instance = await self.get_by_id(instance_id)
        if not instance:
            return {"daily_exceeded": False, "monthly_exceeded": False}
        
        return {
            "daily_exceeded": instance.current_spend_daily >= instance.spend_limit_daily,
            "monthly_exceeded": instance.current_spend_monthly >= instance.spend_limit_monthly
        }
    
    def _row_to_model(self, row: asyncpg.Record) -> PersonaInstance:
        """Convert database row to PersonaInstance model"""
        if not row:
            return None
        
        # Parse JSON fields
        llm_providers = row['llm_providers'] or []
        if isinstance(llm_providers, str):
            llm_providers = json.loads(llm_providers)
        
        custom_settings = row['custom_settings'] or {}
        if isinstance(custom_settings, str):
            custom_settings = json.loads(custom_settings)
        
        # Convert LLM provider dicts to LLMModel objects
        llm_models = [LLMModel(**provider) for provider in llm_providers]
        
        return PersonaInstance(
            id=row['id'],
            instance_name=row['instance_name'],
            persona_type_id=row['persona_type_id'],
            azure_devops_org=row['azure_devops_org'],
            azure_devops_project=row['azure_devops_project'],
            repository_name=row['repository_name'],
            llm_providers=llm_models,
            spend_limit_daily=row['spend_limit_daily'],
            spend_limit_monthly=row['spend_limit_monthly'],
            current_spend_daily=row['current_spend_daily'],
            current_spend_monthly=row['current_spend_monthly'],
            max_concurrent_tasks=row['max_concurrent_tasks'],
            priority_level=row['priority_level'],
            custom_settings=custom_settings,
            is_active=row['is_active'],
            last_activity=row['last_activity'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            # Additional fields from join
            persona_type_name=row.get('persona_type_name'),
            persona_display_name=row.get('persona_display_name')
        )