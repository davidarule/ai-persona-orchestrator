-- Create spend_tracking table for detailed spend records
CREATE TABLE IF NOT EXISTS orchestrator.spend_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    amount NUMERIC(10,4) NOT NULL,
    category TEXT NOT NULL, -- 'llm_usage', 'api_usage', 'compute', etc.
    description TEXT NOT NULL,
    metadata JSONB, -- Additional details about the spend
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_spend_tracking_instance_id ON orchestrator.spend_tracking(instance_id);
CREATE INDEX idx_spend_tracking_category ON orchestrator.spend_tracking(category);
CREATE INDEX idx_spend_tracking_created_at ON orchestrator.spend_tracking(created_at);
CREATE INDEX idx_spend_tracking_amount ON orchestrator.spend_tracking(amount);

-- Create spend_alerts table for threshold monitoring
CREATE TABLE IF NOT EXISTS orchestrator.spend_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    daily_threshold_pct INTEGER NOT NULL DEFAULT 80,
    monthly_threshold_pct INTEGER NOT NULL DEFAULT 80,
    alert_email TEXT,
    alert_webhook TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    UNIQUE(instance_id)
);

-- Create spend_budgets table for project/team budgets
CREATE TABLE IF NOT EXISTS orchestrator.spend_budgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    azure_devops_project TEXT NOT NULL,
    monthly_budget NUMERIC(10,2) NOT NULL,
    current_spend NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Create index for project lookups
CREATE INDEX idx_spend_budgets_project ON orchestrator.spend_budgets(azure_devops_project);

-- Create spend_reports table for generated reports
CREATE TABLE IF NOT EXISTS orchestrator.spend_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type TEXT NOT NULL, -- 'daily', 'weekly', 'monthly'
    report_date DATE NOT NULL,
    project TEXT,
    report_data JSONB NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Create index for report lookups
CREATE INDEX idx_spend_reports_date ON orchestrator.spend_reports(report_date);
CREATE INDEX idx_spend_reports_type ON orchestrator.spend_reports(report_type);
CREATE INDEX idx_spend_reports_project ON orchestrator.spend_reports(project);