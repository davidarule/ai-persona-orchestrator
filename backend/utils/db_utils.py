"""
Database utility functions for AI Persona Orchestrator
"""

import json
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import asyncpg


class QueryBuilder:
    """Helper class for building SQL queries safely"""
    
    @staticmethod
    def insert(table: str, data: Dict[str, Any], schema: str = "orchestrator") -> tuple[str, list]:
        """Build INSERT query with parameters"""
        columns = list(data.keys())
        placeholders = [f"${i+1}" for i in range(len(columns))]
        values = list(data.values())
        
        query = f"""
            INSERT INTO {schema}.{table} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """
        
        return query.strip(), values
    
    @staticmethod
    def bulk_insert(table: str, records: List[Dict[str, Any]], schema: str = "orchestrator") -> tuple[str, List[tuple]]:
        """Build bulk INSERT query"""
        if not records:
            raise ValueError("No records to insert")
        
        columns = list(records[0].keys())
        placeholders = [f"${i+1}" for i in range(len(columns))]
        
        query = f"""
            INSERT INTO {schema}.{table} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
        """
        
        values_list = [tuple(record[col] for col in columns) for record in records]
        
        return query.strip(), values_list
    
    @staticmethod
    def update(
        table: str, 
        data: Dict[str, Any], 
        conditions: Dict[str, Any],
        schema: str = "orchestrator"
    ) -> tuple[str, list]:
        """Build UPDATE query with parameters"""
        set_clauses = []
        values = []
        param_index = 1
        
        # Build SET clauses
        for column, value in data.items():
            set_clauses.append(f"{column} = ${param_index}")
            values.append(value)
            param_index += 1
        
        # Build WHERE clauses
        where_clauses = []
        for column, value in conditions.items():
            where_clauses.append(f"{column} = ${param_index}")
            values.append(value)
            param_index += 1
        
        # Check if table has updated_at column (most do, but not all)
        set_clause_str = ', '.join(set_clauses)
        if table not in ['persona_types', 'mcp_servers', 'mcp_capabilities']:  # Tables without updated_at
            set_clause_str += ', updated_at = NOW()'
        
        query = f"""
            UPDATE {schema}.{table}
            SET {set_clause_str}
            WHERE {' AND '.join(where_clauses)}
            RETURNING *
        """
        
        return query.strip(), values
    
    @staticmethod
    def select(
        table: str,
        columns: Optional[List[str]] = None,
        conditions: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        schema: str = "orchestrator"
    ) -> tuple[str, list]:
        """Build SELECT query with parameters"""
        columns_str = ", ".join(columns) if columns else "*"
        values = []
        
        query_parts = [f"SELECT {columns_str} FROM {schema}.{table}"]
        
        # Add WHERE clause
        if conditions:
            where_clauses = []
            for i, (column, value) in enumerate(conditions.items(), 1):
                if isinstance(value, list):
                    # Handle IN clause
                    placeholders = [f"${j}" for j in range(i, i + len(value))]
                    where_clauses.append(f"{column} IN ({', '.join(placeholders)})")
                    values.extend(value)
                else:
                    where_clauses.append(f"{column} = ${i}")
                    values.append(value)
            
            query_parts.append(f"WHERE {' AND '.join(where_clauses)}")
        
        # Add ORDER BY
        if order_by:
            query_parts.append(f"ORDER BY {order_by}")
        
        # Add LIMIT
        if limit:
            query_parts.append(f"LIMIT {limit}")
        
        # Add OFFSET
        if offset:
            query_parts.append(f"OFFSET {offset}")
        
        return " ".join(query_parts), values


class JSONBHelpers:
    """Helper functions for working with JSONB fields"""
    
    @staticmethod
    def merge_update(column: str, data: Dict[str, Any]) -> str:
        """Build JSONB merge update expression"""
        return f"{column} = {column} || ${len(data) + 1}::jsonb"
    
    @staticmethod
    def path_update(column: str, path: str, value: Any) -> tuple[str, str]:
        """Build JSONB path update expression"""
        # Convert path like "settings.theme" to '{settings,theme}'
        path_parts = path.split('.')
        pg_path = '{' + ','.join(path_parts) + '}'
        
        return f"{column} = jsonb_set({column}, '{pg_path}', $1::jsonb)", json.dumps(value)
    
    @staticmethod
    def array_append(column: str, value: Any) -> tuple[str, str]:
        """Build JSONB array append expression"""
        return f"{column} = {column} || $1::jsonb", json.dumps([value])
    
    @staticmethod
    def array_remove(column: str, value: Any) -> str:
        """Build JSONB array element removal expression"""
        return f"{column} = {column} - $1::text"


def parse_pg_timestamp(timestamp: Any) -> Optional[datetime]:
    """Parse PostgreSQL timestamp to Python datetime"""
    if isinstance(timestamp, datetime):
        return timestamp
    elif isinstance(timestamp, str):
        try:
            return datetime.fromisoformat(timestamp)
        except:
            return None
    return None


def format_pg_array(items: List[Any]) -> str:
    """Format Python list as PostgreSQL array literal"""
    if not items:
        return "{}"
    
    formatted_items = []
    for item in items:
        if isinstance(item, str):
            # Escape quotes and backslashes
            escaped = item.replace("\\", "\\\\").replace('"', '\\"')
            formatted_items.append(f'"{escaped}"')
        else:
            formatted_items.append(str(item))
    
    return "{" + ",".join(formatted_items) + "}"


async def get_table_row_count(conn: asyncpg.Connection, table: str, schema: str = "orchestrator") -> int:
    """Get row count for a table"""
    query = f"SELECT COUNT(*) FROM {schema}.{table}"
    count = await conn.fetchval(query)
    return count


async def table_exists(conn: asyncpg.Connection, table: str, schema: str = "orchestrator") -> bool:
    """Check if a table exists"""
    query = """
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.tables 
            WHERE table_schema = $1 
            AND table_name = $2
        )
    """
    exists = await conn.fetchval(query, schema, table)
    return exists


async def get_table_columns(conn: asyncpg.Connection, table: str, schema: str = "orchestrator") -> List[Dict[str, Any]]:
    """Get column information for a table"""
    query = """
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
    """
    
    rows = await conn.fetch(query, schema, table)
    
    return [
        {
            "name": row["column_name"],
            "type": row["data_type"],
            "nullable": row["is_nullable"] == "YES",
            "default": row["column_default"],
            "max_length": row["character_maximum_length"]
        }
        for row in rows
    ]


class DatabaseTransaction:
    """Context manager for database transactions with automatic rollback"""
    
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
        self.transaction = None
    
    async def __aenter__(self):
        self.transaction = self.conn.transaction()
        await self.transaction.start()
        return self.conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Rollback on exception
            await self.transaction.rollback()
        else:
            # Commit on success
            await self.transaction.commit()


# Schema validation helpers
def validate_persona_instance(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean persona instance data"""
    required_fields = ["instance_name", "persona_type_id", "azure_devops_project"]
    
    for field in required_fields:
        if field not in data or not data[field]:
            raise ValueError(f"Missing required field: {field}")
    
    # Ensure JSONB fields are properly formatted
    if "llm_providers" in data and isinstance(data["llm_providers"], dict):
        data["llm_providers"] = json.dumps(data["llm_providers"])
    
    if "custom_settings" in data and isinstance(data["custom_settings"], dict):
        data["custom_settings"] = json.dumps(data["custom_settings"])
    
    return data


def validate_workflow_execution(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean workflow execution data"""
    required_fields = ["workflow_id", "work_item_id"]
    
    for field in required_fields:
        if field not in data or not data[field]:
            raise ValueError(f"Missing required field: {field}")
    
    # Set defaults
    data.setdefault("status", "pending")
    data.setdefault("current_phase", "initialization")
    data.setdefault("sync_status", "synced")
    
    # Ensure JSONB fields
    if "langgraph_state" in data and isinstance(data["langgraph_state"], dict):
        data["langgraph_state"] = json.dumps(data["langgraph_state"])
    
    return data