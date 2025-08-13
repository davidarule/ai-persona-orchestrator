-- Create database schema for AI Orchestrator
CREATE SCHEMA IF NOT EXISTS orchestrator;

-- Workflow status tracking table
CREATE TABLE IF NOT EXISTS orchestrator.workflow_status (
    id SERIAL PRIMARY KEY,
    work_item_id VARCHAR(255) NOT NULL,
    workflow_id VARCHAR(255) NOT NULL,
    step_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    agent_id VARCHAR(255),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent status table
CREATE TABLE IF NOT EXISTS orchestrator.agent_status (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(255) NOT NULL,
    agent_type VARCHAR(100),
    status VARCHAR(50) NOT NULL,
    current_task VARCHAR(500),
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    configuration JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Workflow definitions table
CREATE TABLE IF NOT EXISTS orchestrator.workflow_definitions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    version VARCHAR(50) NOT NULL,
    definition_yaml TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Work items table
CREATE TABLE IF NOT EXISTS orchestrator.work_items (
    id SERIAL PRIMARY KEY,
    work_item_id VARCHAR(255) UNIQUE NOT NULL,
    title VARCHAR(500),
    description TEXT,
    type VARCHAR(100),
    assigned_agents JSONB,
    azure_devops_data JSONB,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_workflow_status_work_item ON orchestrator.workflow_status(work_item_id);
CREATE INDEX idx_workflow_status_workflow ON orchestrator.workflow_status(workflow_id);
CREATE INDEX idx_agent_status_name ON orchestrator.agent_status(agent_name);
CREATE INDEX idx_work_items_status ON orchestrator.work_items(status);

-- Create update trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_workflow_status_updated_at BEFORE UPDATE
    ON orchestrator.workflow_status FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflow_definitions_updated_at BEFORE UPDATE
    ON orchestrator.workflow_definitions FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_work_items_updated_at BEFORE UPDATE
    ON orchestrator.work_items FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA orchestrator TO orchestrator_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA orchestrator TO orchestrator_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA orchestrator TO orchestrator_user;
