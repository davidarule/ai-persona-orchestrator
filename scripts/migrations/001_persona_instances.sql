-- Migration 001: Add Persona Instance Management Tables
-- Description: Creates tables for persona types, instances, and related functionality
-- Author: AI Persona Orchestrator
-- Date: 2025-01-14

-- Start transaction
BEGIN;

-- 1. Persona Instance Management
CREATE TABLE orchestrator.persona_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type_name VARCHAR(100) UNIQUE NOT NULL, -- e.g., 'software-architect'
    display_name VARCHAR(255) NOT NULL,      -- e.g., 'Software Architect'
    base_workflow_id VARCHAR(255),           -- Reference to persona workflow
    default_capabilities JSONB,              -- Default capabilities for this type
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orchestrator.persona_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_name VARCHAR(255) NOT NULL,     -- e.g., 'Steve Bot - Project Alpha'
    persona_type_id UUID REFERENCES orchestrator.persona_types(id),
    
    -- Project Assignment (one project per instance)
    azure_devops_org VARCHAR(500),
    azure_devops_project VARCHAR(500),
    repository_name VARCHAR(500),
    
    -- LLM Configuration
    llm_providers JSONB,  -- Priority-ordered list with models
    spend_limit_daily DECIMAL(10,2),
    spend_limit_monthly DECIMAL(10,2),
    current_spend_daily DECIMAL(10,2) DEFAULT 0,
    current_spend_monthly DECIMAL(10,2) DEFAULT 0,
    
    -- Instance Configuration
    max_concurrent_tasks INTEGER DEFAULT 5,
    priority_level INTEGER DEFAULT 0,
    custom_settings JSONB,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    last_activity TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(instance_name, azure_devops_project)
);

-- 2. MCP Server Registry
CREATE TABLE orchestrator.mcp_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_name VARCHAR(100) UNIQUE NOT NULL,
    server_type VARCHAR(50),
    connection_config JSONB,
    is_deployed BOOLEAN DEFAULT false,
    health_check_url VARCHAR(500),
    last_health_check TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orchestrator.mcp_capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id UUID REFERENCES orchestrator.mcp_servers(id) ON DELETE CASCADE,
    capability_name VARCHAR(255) NOT NULL,
    capability_type VARCHAR(100),
    description TEXT,
    parameters_schema JSONB,
    response_schema JSONB,
    rate_limit INTEGER,
    timeout_ms INTEGER DEFAULT 30000,
    is_available BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(server_id, capability_name)
);

CREATE TABLE orchestrator.persona_mcp_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_instance_id UUID REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    capability_id UUID REFERENCES orchestrator.mcp_capabilities(id) ON DELETE CASCADE,
    can_read BOOLEAN DEFAULT true,
    can_write BOOLEAN DEFAULT false,
    can_execute BOOLEAN DEFAULT true,
    custom_rate_limit INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(persona_instance_id, capability_id)
);

-- 3. Performance Indexes
CREATE INDEX idx_persona_instances_project ON orchestrator.persona_instances(azure_devops_project);
CREATE INDEX idx_persona_instances_type ON orchestrator.persona_instances(persona_type_id);
CREATE INDEX idx_persona_instances_active ON orchestrator.persona_instances(is_active);
CREATE INDEX idx_mcp_capabilities_server ON orchestrator.mcp_capabilities(server_id);
CREATE INDEX idx_persona_mcp_permissions_persona ON orchestrator.persona_mcp_permissions(persona_instance_id);
CREATE INDEX idx_persona_mcp_permissions_capability ON orchestrator.persona_mcp_permissions(capability_id);

-- 4. Update Triggers
CREATE TRIGGER update_persona_instances_updated_at 
    BEFORE UPDATE ON orchestrator.persona_instances 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Add comments
COMMENT ON TABLE orchestrator.persona_types IS 'Defines the 25 abstract persona types (e.g., Software Architect, QA Engineer)';
COMMENT ON TABLE orchestrator.persona_instances IS 'Concrete instances of personas assigned to specific projects';
COMMENT ON TABLE orchestrator.mcp_servers IS 'Registry of 8 MCP servers providing capabilities to personas';
COMMENT ON TABLE orchestrator.mcp_capabilities IS 'Discoverable capabilities provided by each MCP server';
COMMENT ON TABLE orchestrator.persona_mcp_permissions IS 'Maps which persona instances can use which MCP capabilities';

COMMENT ON COLUMN orchestrator.persona_instances.llm_providers IS 'JSON array of LLM providers in priority order, e.g., [{"provider": "openai", "model": "gpt-4", "priority": 1}]';
COMMENT ON COLUMN orchestrator.persona_instances.spend_limit_daily IS 'Daily spending limit in USD for LLM API calls';
COMMENT ON COLUMN orchestrator.persona_instances.azure_devops_project IS 'One persona instance can only work on one project to avoid context confusion';

-- Commit transaction
COMMIT;

-- Rollback script (save as 001_persona_instances_rollback.sql)
/*
BEGIN;
DROP TABLE IF EXISTS orchestrator.persona_mcp_permissions CASCADE;
DROP TABLE IF EXISTS orchestrator.mcp_capabilities CASCADE;
DROP TABLE IF EXISTS orchestrator.mcp_servers CASCADE;
DROP TABLE IF EXISTS orchestrator.persona_instances CASCADE;
DROP TABLE IF EXISTS orchestrator.persona_types CASCADE;
COMMIT;
*/