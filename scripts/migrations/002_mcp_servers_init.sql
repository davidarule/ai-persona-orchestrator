-- Migration 002: Initialize MCP Servers
-- Description: Inserts the 8 MCP servers into the registry
-- Author: AI Persona Orchestrator
-- Date: 2025-01-14

BEGIN;

-- Insert the 8 MCP servers
INSERT INTO orchestrator.mcp_servers (server_name, server_type, connection_config, is_deployed) VALUES
('Memory', 'memory', 
 '{"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"], "description": "Temporary context storage for personas"}', 
 false),

('File System', 'filesystem', 
 '{"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"], "description": "File system access for code operations"}', 
 false),

('GitHub', 'github', 
 '{"command": "mcp-server-github", "args": [], "description": "GitHub repository operations and PR management"}', 
 false),

('PostgreSQL', 'database', 
 '{"command": "mcp-server-postgres", "args": ["--readonly"], "description": "Read-only database queries"}', 
 false),

('Context7', 'documentation', 
 '{"command": "context7-server", "args": ["--port", "5001"], "description": "Documentation retrieval and context"}', 
 false),

('Serena', 'code-analysis', 
 '{"command": "serena-server", "args": ["--config", "/config/serena.json"], "description": "Semantic code analysis and search"}', 
 false),

('Memory Bank', 'persistent-memory', 
 '{"command": "memory-bank-server", "args": ["--db", "/data/memory-bank.db"], "description": "Persistent memory storage across sessions"}', 
 false),

('Nova', 'reasoning', 
 '{"command": "nova-server", "args": [], "description": "Advanced reasoning and constraint solving"}', 
 false);

-- Add initial capabilities for Memory server as example
INSERT INTO orchestrator.mcp_capabilities (server_id, capability_name, capability_type, description, parameters_schema, response_schema) 
SELECT 
    id,
    'store_context',
    'command',
    'Store context information with optional TTL',
    '{"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "object"}, "ttl": {"type": "integer"}}, "required": ["key", "value"]}',
    '{"type": "object", "properties": {"success": {"type": "boolean"}, "key": {"type": "string"}}}'
FROM orchestrator.mcp_servers WHERE server_name = 'Memory';

INSERT INTO orchestrator.mcp_capabilities (server_id, capability_name, capability_type, description, parameters_schema, response_schema) 
SELECT 
    id,
    'retrieve_context',
    'query',
    'Retrieve stored context by key with fuzzy matching option',
    '{"type": "object", "properties": {"key": {"type": "string"}, "fuzzy": {"type": "boolean"}}, "required": ["key"]}',
    '{"type": "object", "properties": {"value": {"type": "object"}, "metadata": {"type": "object"}}}'
FROM orchestrator.mcp_servers WHERE server_name = 'Memory';

-- Add initial capabilities for GitHub server
INSERT INTO orchestrator.mcp_capabilities (server_id, capability_name, capability_type, description, parameters_schema, response_schema) 
SELECT 
    id,
    'create_pull_request',
    'command',
    'Create a new pull request',
    '{"type": "object", "properties": {"repo": {"type": "string"}, "branch": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, "required": ["repo", "branch", "title"]}',
    '{"type": "object", "properties": {"pr_number": {"type": "integer"}, "url": {"type": "string"}}}'
FROM orchestrator.mcp_servers WHERE server_name = 'GitHub';

COMMIT;

-- Verify insertion
-- SELECT server_name, server_type, is_deployed FROM orchestrator.mcp_servers ORDER BY created_at;