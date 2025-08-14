"""
Unit tests for database utilities
"""

import pytest
import json
from datetime import datetime
from backend.utils.db_utils import (
    QueryBuilder, JSONBHelpers, parse_pg_timestamp, 
    format_pg_array, validate_persona_instance, validate_workflow_execution
)


class TestQueryBuilder:
    """Test SQL query builder"""
    
    def test_insert_query(self):
        """Test INSERT query generation"""
        data = {
            "name": "Test Instance",
            "type_id": "123",
            "is_active": True
        }
        
        query, values = QueryBuilder.insert("test_table", data)
        
        assert "INSERT INTO orchestrator.test_table" in query
        assert "(name, type_id, is_active)" in query
        assert "VALUES ($1, $2, $3)" in query
        assert values == ["Test Instance", "123", True]
    
    def test_bulk_insert_query(self):
        """Test bulk INSERT query generation"""
        records = [
            {"name": "Test1", "value": 1},
            {"name": "Test2", "value": 2}
        ]
        
        query, values_list = QueryBuilder.bulk_insert("test_table", records)
        
        assert "INSERT INTO orchestrator.test_table" in query
        assert "(name, value)" in query
        assert "VALUES ($1, $2)" in query
        assert values_list == [("Test1", 1), ("Test2", 2)]
    
    def test_update_query(self):
        """Test UPDATE query generation"""
        data = {"name": "Updated", "status": "active"}
        conditions = {"id": "123"}
        
        query, values = QueryBuilder.update("test_table", data, conditions)
        
        assert "UPDATE orchestrator.test_table" in query
        assert "SET name = $1, status = $2" in query
        assert "WHERE id = $3" in query
        assert values == ["Updated", "active", "123"]
    
    def test_select_query_simple(self):
        """Test simple SELECT query"""
        query, values = QueryBuilder.select("test_table")
        
        assert query == "SELECT * FROM orchestrator.test_table"
        assert values == []
    
    def test_select_query_with_conditions(self):
        """Test SELECT with WHERE conditions"""
        conditions = {"status": "active", "type": "test"}
        
        query, values = QueryBuilder.select(
            "test_table",
            columns=["id", "name"],
            conditions=conditions,
            order_by="created_at DESC",
            limit=10
        )
        
        assert "SELECT id, name FROM orchestrator.test_table" in query
        assert "WHERE status = $1 AND type = $2" in query
        assert "ORDER BY created_at DESC" in query
        assert "LIMIT 10" in query
        assert values == ["active", "test"]
    
    def test_select_query_with_in_clause(self):
        """Test SELECT with IN clause"""
        conditions = {"id": ["1", "2", "3"]}
        
        query, values = QueryBuilder.select("test_table", conditions=conditions)
        
        assert "WHERE id IN ($1, $2, $3)" in query
        assert values == ["1", "2", "3"]


class TestJSONBHelpers:
    """Test JSONB helper functions"""
    
    def test_merge_update(self):
        """Test JSONB merge update expression"""
        data = {"theme": "dark", "lang": "en"}
        expr = JSONBHelpers.merge_update("settings", data)
        
        # The parameter number depends on the number of items in data
        assert expr == f"settings = settings || ${len(data) + 1}::jsonb"
    
    def test_path_update(self):
        """Test JSONB path update expression"""
        expr, value = JSONBHelpers.path_update("config", "ui.theme", "dark")
        
        assert expr == "config = jsonb_set(config, '{ui,theme}', $1::jsonb)"
        assert value == '"dark"'
    
    def test_array_append(self):
        """Test JSONB array append expression"""
        expr, value = JSONBHelpers.array_append("tags", "new-tag")
        
        assert expr == "tags = tags || $1::jsonb"
        assert value == '["new-tag"]'
    
    def test_array_remove(self):
        """Test JSONB array element removal"""
        expr = JSONBHelpers.array_remove("tags", "old-tag")
        
        assert expr == "tags = tags - $1::text"


class TestHelperFunctions:
    """Test utility helper functions"""
    
    def test_parse_pg_timestamp(self):
        """Test PostgreSQL timestamp parsing"""
        # Test with datetime object
        dt = datetime(2024, 1, 14, 12, 30, 45)
        result = parse_pg_timestamp(dt)
        assert result == dt
        
        # Test with ISO string
        iso_str = "2024-01-14T12:30:45"
        result = parse_pg_timestamp(iso_str)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        
        # Test with invalid input
        assert parse_pg_timestamp("invalid") is None
        assert parse_pg_timestamp(None) is None
    
    def test_format_pg_array(self):
        """Test PostgreSQL array formatting"""
        # Empty array
        assert format_pg_array([]) == "{}"
        
        # String array
        assert format_pg_array(["a", "b", "c"]) == '{"a","b","c"}'
        
        # String with quotes
        assert format_pg_array(['test"quote']) == '{"test\\"quote"}'
        
        # Mixed types
        assert format_pg_array(["text", 123, True]) == '{"text",123,True}'


class TestValidators:
    """Test data validators"""
    
    def test_validate_persona_instance_valid(self):
        """Test valid persona instance validation"""
        data = {
            "instance_name": "Test Bot",
            "persona_type_id": "123",
            "azure_devops_project": "Test Project",
            "llm_providers": {"primary": "openai"},
            "custom_settings": {"theme": "dark"}
        }
        
        result = validate_persona_instance(data)
        
        assert result["instance_name"] == "Test Bot"
        assert isinstance(result["llm_providers"], str)
        assert isinstance(result["custom_settings"], str)
    
    def test_validate_persona_instance_missing_field(self):
        """Test persona instance validation with missing field"""
        data = {
            "instance_name": "Test Bot",
            "persona_type_id": "123"
            # Missing azure_devops_project
        }
        
        with pytest.raises(ValueError, match="Missing required field: azure_devops_project"):
            validate_persona_instance(data)
    
    def test_validate_workflow_execution_valid(self):
        """Test valid workflow execution validation"""
        data = {
            "workflow_id": "wf0-feature-development",
            "work_item_id": "12345",
            "langgraph_state": {"phase": "init"}
        }
        
        result = validate_workflow_execution(data)
        
        assert result["workflow_id"] == "wf0-feature-development"
        assert result["status"] == "pending"  # Default added
        assert result["current_phase"] == "initialization"  # Default added
        assert isinstance(result["langgraph_state"], str)
    
    def test_validate_workflow_execution_defaults(self):
        """Test workflow execution validation adds defaults"""
        data = {
            "workflow_id": "wf1",
            "work_item_id": "123"
        }
        
        result = validate_workflow_execution(data)
        
        assert result["status"] == "pending"
        assert result["current_phase"] == "initialization"
        assert result["sync_status"] == "synced"