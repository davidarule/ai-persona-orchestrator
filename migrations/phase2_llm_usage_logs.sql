-- Create llm_usage_logs table for tracking LLM provider usage
CREATE TABLE IF NOT EXISTS orchestrator.llm_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost NUMERIC(10,4) NOT NULL,
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_llm_usage_instance_id ON orchestrator.llm_usage_logs(instance_id);
CREATE INDEX idx_llm_usage_created_at ON orchestrator.llm_usage_logs(created_at);
CREATE INDEX idx_llm_usage_provider ON orchestrator.llm_usage_logs(provider);