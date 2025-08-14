-- Migration 003: RACI and Communication Tables
-- Description: Creates RACI matrix, persona communication, and workflow state sync tables
-- Author: AI Persona Orchestrator
-- Date: 2025-01-14

BEGIN;

-- 1. RACI Matrix Definition
CREATE TABLE orchestrator.raci_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id VARCHAR(100),
    phase VARCHAR(100),
    task_type VARCHAR(100),
    responsible JSONB DEFAULT '[]',     -- Array of persona types
    accountable JSONB DEFAULT '[]',
    consulted JSONB DEFAULT '[]',
    informed JSONB DEFAULT '[]',
    min_approvals INTEGER DEFAULT 1,
    escalation_timeout INTEGER,         -- seconds before escalation
    auto_approve_conditions JSONB,
    veto_power JSONB DEFAULT '[]',      -- Personas who can block
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. Persona Communication
CREATE TABLE orchestrator.persona_communications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id VARCHAR(255) UNIQUE NOT NULL,
    correlation_id VARCHAR(255),
    
    -- Participants
    sender_persona_id UUID REFERENCES orchestrator.persona_instances(id) ON DELETE SET NULL,
    recipient_persona_id UUID REFERENCES orchestrator.persona_instances(id) ON DELETE SET NULL,
    cc_personas JSONB DEFAULT '[]',
    
    -- Message Details
    workflow_execution_id UUID,
    message_type VARCHAR(50), -- handoff, consultation, escalation, inform
    priority VARCHAR(20),     -- critical, high, medium, low
    subject TEXT,
    
    -- Payload
    body JSONB,
    context JSONB,
    attachments JSONB DEFAULT '[]',
    
    -- Protocol
    requires_acknowledgment BOOLEAN DEFAULT false,
    acknowledgment_timeout INTEGER,
    requires_response BOOLEAN DEFAULT false,
    response_timeout INTEGER,
    
    -- Status Tracking
    status VARCHAR(50) DEFAULT 'sent',
    acknowledged_at TIMESTAMP,
    response JSONB,
    processed_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- 3. Workflow State Synchronization
CREATE TABLE orchestrator.workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id VARCHAR(100),
    work_item_id VARCHAR(255),
    
    -- State Management
    langgraph_state JSONB,
    camunda_process_id VARCHAR(255),
    current_phase VARCHAR(100),
    sync_status VARCHAR(50),
    
    -- Execution Details
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(50),
    error_details JSONB,
    
    -- Participants
    assigned_personas JSONB DEFAULT '[]',
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orchestrator.workflow_state_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID REFERENCES orchestrator.workflow_executions(id) ON DELETE CASCADE,
    source VARCHAR(50), -- 'langgraph' or 'camunda'
    event_type VARCHAR(100),
    payload JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 4. Performance Indexes
CREATE INDEX idx_raci_workflow ON orchestrator.raci_definitions(workflow_id);
CREATE INDEX idx_raci_phase ON orchestrator.raci_definitions(phase);
CREATE INDEX idx_persona_comm_workflow ON orchestrator.persona_communications(workflow_execution_id);
CREATE INDEX idx_persona_comm_status ON orchestrator.persona_communications(status);
CREATE INDEX idx_persona_comm_created ON orchestrator.persona_communications(created_at DESC);
CREATE INDEX idx_persona_comm_sender ON orchestrator.persona_communications(sender_persona_id);
CREATE INDEX idx_persona_comm_recipient ON orchestrator.persona_communications(recipient_persona_id);
CREATE INDEX idx_workflow_exec_status ON orchestrator.workflow_executions(status);
CREATE INDEX idx_workflow_exec_item ON orchestrator.workflow_executions(work_item_id);
CREATE INDEX idx_workflow_state_events_exec ON orchestrator.workflow_state_events(execution_id);
CREATE INDEX idx_workflow_state_events_created ON orchestrator.workflow_state_events(created_at DESC);

-- 5. Update Triggers
CREATE TRIGGER update_raci_definitions_updated_at 
    BEFORE UPDATE ON orchestrator.raci_definitions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflow_executions_updated_at 
    BEFORE UPDATE ON orchestrator.workflow_executions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 6. Add Comments
COMMENT ON TABLE orchestrator.raci_definitions IS 'RACI matrix defining responsibilities for workflow phases';
COMMENT ON TABLE orchestrator.persona_communications IS 'Inter-persona messaging with acknowledgment and response tracking';
COMMENT ON TABLE orchestrator.workflow_executions IS 'Active workflow execution state synchronized between LangGraph and Camunda';
COMMENT ON TABLE orchestrator.workflow_state_events IS 'Event stream for workflow state changes from both orchestrators';

COMMENT ON COLUMN orchestrator.raci_definitions.responsible IS 'Array of persona types responsible for executing the task';
COMMENT ON COLUMN orchestrator.raci_definitions.accountable IS 'Array of persona types accountable for the outcome';
COMMENT ON COLUMN orchestrator.raci_definitions.consulted IS 'Array of persona types to be consulted';
COMMENT ON COLUMN orchestrator.raci_definitions.informed IS 'Array of persona types to be informed';

COMMENT ON COLUMN orchestrator.persona_communications.message_type IS 'Type: handoff, consultation, escalation, inform, acknowledgment';
COMMENT ON COLUMN orchestrator.persona_communications.priority IS 'Priority: critical (immediate), high (1hr), medium (4hr), low (when available)';

COMMIT;