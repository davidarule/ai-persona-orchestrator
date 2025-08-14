"""
Repository for PersonaType database operations
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
import asyncpg
from datetime import datetime
import json

from backend.models.persona_type import (
    PersonaType, 
    PersonaTypeCreate, 
    PersonaTypeUpdate,
    PersonaCategory
)
from backend.services.database import DatabaseManager
from backend.utils.db_utils import QueryBuilder


class PersonaTypeRepository:
    """Repository for managing PersonaType entities in the database"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.schema = "orchestrator"
        self.table = "persona_types"
        
    async def create(self, persona_type: PersonaTypeCreate) -> PersonaType:
        """Create a new persona type"""
        query = f"""
        INSERT INTO {self.schema}.{self.table} (
            type_name, display_name, base_workflow_id, default_capabilities
        ) VALUES ($1, $2, $3, $4)
        RETURNING *
        """
        
        # Prepare the data
        values = [
            persona_type.type_name,
            persona_type.display_name,
            persona_type.base_workflow_id,
            json.dumps(persona_type.default_capabilities)
        ]
        
        row = await self.db.execute_query(query, *values, fetch_one=True)
        
        if row:
            # Store additional fields in a separate metadata table or as part of capabilities
            enriched_capabilities = {
                **persona_type.default_capabilities,
                "category": persona_type.category,
                "description": persona_type.description,
                "required_skills": persona_type.required_skills,
                "compatible_workflows": persona_type.compatible_workflows
            }
            
            # Update with enriched capabilities
            update_query = f"""
            UPDATE {self.schema}.{self.table} 
            SET default_capabilities = $1
            WHERE id = $2
            RETURNING *
            """
            
            row = await self.db.execute_query(
                update_query, 
                json.dumps(enriched_capabilities), 
                row['id'], 
                fetch_one=True
            )
            
            return self._row_to_model(row)
        
        raise ValueError("Failed to create persona type")
    
    async def get_by_id(self, persona_id: UUID) -> Optional[PersonaType]:
        """Get a persona type by ID"""
        query = f"SELECT * FROM {self.schema}.{self.table} WHERE id = $1"
        row = await self.db.execute_query(query, persona_id, fetch_one=True)
        return self._row_to_model(row) if row else None
    
    async def get_by_type_name(self, type_name: str) -> Optional[PersonaType]:
        """Get a persona type by type_name"""
        query = f"SELECT * FROM {self.schema}.{self.table} WHERE type_name = $1"
        row = await self.db.execute_query(query, type_name, fetch_one=True)
        return self._row_to_model(row) if row else None
    
    async def list_all(
        self, 
        category: Optional[PersonaCategory] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PersonaType]:
        """List all persona types with optional filtering"""
        if category:
            query = f"""
            SELECT * FROM {self.schema}.{self.table} 
            WHERE default_capabilities->>'category' = $1
            ORDER BY display_name
            LIMIT $2 OFFSET $3
            """
            rows = await self.db.execute_query(query, category, limit, offset)
        else:
            query = f"""
            SELECT * FROM {self.schema}.{self.table} 
            ORDER BY display_name
            LIMIT $1 OFFSET $2
            """
            rows = await self.db.execute_query(query, limit, offset)
        
        return [self._row_to_model(row) for row in rows]
    
    async def update(
        self, 
        persona_id: UUID, 
        update_data: PersonaTypeUpdate
    ) -> Optional[PersonaType]:
        """Update a persona type"""
        # Get current data
        current = await self.get_by_id(persona_id)
        if not current:
            return None
        
        # Build update query dynamically
        updates = {}
        
        if update_data.display_name is not None:
            updates['display_name'] = update_data.display_name
            
        if update_data.base_workflow_id is not None:
            updates['base_workflow_id'] = update_data.base_workflow_id
        
        # Handle capabilities update
        if any([
            update_data.default_capabilities is not None,
            update_data.category is not None,
            update_data.description is not None,
            update_data.required_skills is not None,
            update_data.compatible_workflows is not None
        ]):
            capabilities = dict(current.default_capabilities)
            
            if update_data.default_capabilities is not None:
                capabilities.update(update_data.default_capabilities)
            if update_data.category is not None:
                capabilities['category'] = update_data.category
            if update_data.description is not None:
                capabilities['description'] = update_data.description
            if update_data.required_skills is not None:
                capabilities['required_skills'] = update_data.required_skills
            if update_data.compatible_workflows is not None:
                capabilities['compatible_workflows'] = update_data.compatible_workflows
                
            updates['default_capabilities'] = json.dumps(capabilities)
        
        if not updates:
            return current
        
        # Build and execute update query
        query, params = QueryBuilder.update(
            self.table,
            updates,
            {"id": persona_id},
            schema=self.schema
        )
        
        row = await self.db.execute_query(query, *params, fetch_one=True)
        return self._row_to_model(row) if row else None
    
    async def delete(self, persona_id: UUID) -> bool:
        """Delete a persona type (soft delete by marking inactive)"""
        # Check if there are active instances
        instance_count = await self.count_instances(persona_id)
        if instance_count > 0:
            raise ValueError(
                f"Cannot delete persona type with {instance_count} active instances"
            )
        
        query = f"DELETE FROM {self.schema}.{self.table} WHERE id = $1"
        result = await self.db.execute_query(query, persona_id)
        return result is not None
    
    async def count_instances(self, persona_type_id: UUID) -> int:
        """Count active instances of a persona type"""
        query = """
        SELECT COUNT(*) as count 
        FROM orchestrator.persona_instances 
        WHERE persona_type_id = $1 AND is_active = true
        """
        row = await self.db.execute_query(query, persona_type_id, fetch_one=True)
        return row['count'] if row else 0
    
    async def get_compatible_workflows(self, persona_type_id: UUID) -> List[str]:
        """Get list of compatible workflows for a persona type"""
        persona = await self.get_by_id(persona_type_id)
        if not persona:
            return []
        
        capabilities = persona.default_capabilities
        return capabilities.get('compatible_workflows', [])
    
    async def bulk_create(self, persona_types: List[PersonaTypeCreate]) -> List[PersonaType]:
        """Create multiple persona types in a single transaction"""
        created = []
        
        async with self.db.pg_pool.acquire() as conn:
            async with conn.transaction():
                for persona_type in persona_types:
                    query = f"""
                    INSERT INTO {self.schema}.{self.table} (
                        type_name, display_name, base_workflow_id, default_capabilities
                    ) VALUES ($1, $2, $3, $4)
                    ON CONFLICT (type_name) DO UPDATE
                    SET display_name = EXCLUDED.display_name,
                        base_workflow_id = EXCLUDED.base_workflow_id,
                        default_capabilities = EXCLUDED.default_capabilities
                    RETURNING *
                    """
                    
                    capabilities = {
                        **persona_type.default_capabilities,
                        "category": persona_type.category,
                        "description": persona_type.description,
                        "required_skills": persona_type.required_skills,
                        "compatible_workflows": persona_type.compatible_workflows
                    }
                    
                    row = await conn.fetchrow(
                        query,
                        persona_type.type_name,
                        persona_type.display_name,
                        persona_type.base_workflow_id,
                        json.dumps(capabilities)
                    )
                    
                    if row:
                        created.append(self._row_to_model(row))
        
        return created
    
    def _row_to_model(self, row: asyncpg.Record) -> PersonaType:
        """Convert database row to PersonaType model"""
        if not row:
            return None
            
        # Parse JSON field
        capabilities = row['default_capabilities'] or {}
        if isinstance(capabilities, str):
            capabilities = json.loads(capabilities) if capabilities else {}
        
        return PersonaType(
            id=row['id'],
            type_name=row['type_name'],
            display_name=row['display_name'],
            base_workflow_id=row['base_workflow_id'],
            default_capabilities=capabilities,
            created_at=row['created_at'],
            category=capabilities.get('category', PersonaCategory.SPECIALIZED),
            description=capabilities.get('description'),
            required_skills=capabilities.get('required_skills', []),
            compatible_workflows=capabilities.get('compatible_workflows', [])
        )