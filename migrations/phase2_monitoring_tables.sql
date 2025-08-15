-- Phase 2: Persona Instance Monitoring Tables
-- Tables for metrics collection, alerting, and monitoring data

-- Instance metrics time-series data
CREATE TABLE IF NOT EXISTS orchestrator.instance_metrics (
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    metric_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    metadata JSONB,
    
    -- Primary key on instance, metric type, and timestamp
    PRIMARY KEY (instance_id, metric_type, timestamp),
    
    -- Check valid metric types
    CONSTRAINT valid_metric_type CHECK (metric_type IN (
        'response_time', 'token_usage', 'error_rate', 'cost_per_task',
        'availability', 'task_completion', 'state_duration', 'health_score'
    ))
);

-- Indexes for efficient querying
CREATE INDEX idx_metrics_instance_time ON orchestrator.instance_metrics(instance_id, timestamp DESC);
CREATE INDEX idx_metrics_type_time ON orchestrator.instance_metrics(metric_type, timestamp DESC);

-- Monitoring alerts
CREATE TABLE IF NOT EXISTS orchestrator.monitoring_alerts (
    id UUID PRIMARY KEY,
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved BOOLEAN DEFAULT false,
    resolved_at TIMESTAMP WITH TIME ZONE,
    acknowledged BOOLEAN DEFAULT false,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    
    -- Constraints
    CONSTRAINT valid_alert_type CHECK (alert_type IN (
        'high_error_rate', 'spend_threshold', 'performance_degradation',
        'instance_unhealthy', 'prolonged_busy_state', 'anomaly_detected', 'sla_violation'
    )),
    CONSTRAINT valid_severity CHECK (severity IN ('info', 'warning', 'error', 'critical'))
);

CREATE INDEX idx_alerts_instance ON orchestrator.monitoring_alerts(instance_id, created_at DESC);
CREATE INDEX idx_alerts_unresolved ON orchestrator.monitoring_alerts(resolved, created_at DESC) WHERE NOT resolved;
CREATE INDEX idx_alerts_severity ON orchestrator.monitoring_alerts(severity, created_at DESC);

-- SLA targets configuration
CREATE TABLE IF NOT EXISTS orchestrator.sla_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    metric_type VARCHAR(50) NOT NULL,
    target_value DOUBLE PRECISION NOT NULL,
    comparison VARCHAR(20) NOT NULL,
    measurement_window INTERVAL NOT NULL,
    violation_threshold INTEGER DEFAULT 1,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_sla_metric CHECK (metric_type IN (
        'response_time', 'token_usage', 'error_rate', 'cost_per_task',
        'availability', 'task_completion', 'state_duration', 'health_score'
    )),
    CONSTRAINT valid_comparison CHECK (comparison IN ('less_than', 'greater_than', 'equal_to'))
);

CREATE INDEX idx_sla_instance ON orchestrator.sla_targets(instance_id);
CREATE INDEX idx_sla_enabled ON orchestrator.sla_targets(enabled) WHERE enabled = true;

-- Monitoring dashboards configuration
CREATE TABLE IF NOT EXISTS orchestrator.monitoring_dashboards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    dashboard_config JSONB NOT NULL,
    owner VARCHAR(100),
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_dashboards_owner ON orchestrator.monitoring_dashboards(owner);
CREATE INDEX idx_dashboards_public ON orchestrator.monitoring_dashboards(is_public) WHERE is_public = true;

-- Alert rules configuration
CREATE TABLE IF NOT EXISTS orchestrator.alert_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name VARCHAR(255) NOT NULL,
    description TEXT,
    metric_type VARCHAR(50) NOT NULL,
    condition JSONB NOT NULL, -- e.g., {"operator": ">", "threshold": 0.1, "duration": "5m"}
    severity VARCHAR(20) NOT NULL,
    notification_channels JSONB, -- e.g., ["email", "slack", "webhook"]
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_rule_metric CHECK (metric_type IN (
        'response_time', 'token_usage', 'error_rate', 'cost_per_task',
        'availability', 'task_completion', 'state_duration', 'health_score'
    )),
    CONSTRAINT valid_rule_severity CHECK (severity IN ('info', 'warning', 'error', 'critical'))
);

CREATE INDEX idx_alert_rules_enabled ON orchestrator.alert_rules(enabled) WHERE enabled = true;

-- Metric aggregations for performance
CREATE TABLE IF NOT EXISTS orchestrator.metric_aggregations (
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    metric_type VARCHAR(50) NOT NULL,
    aggregation_period VARCHAR(20) NOT NULL, -- hour, day, week, month
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    min_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    avg_value DOUBLE PRECISION,
    sum_value DOUBLE PRECISION,
    count INTEGER,
    percentile_50 DOUBLE PRECISION,
    percentile_95 DOUBLE PRECISION,
    percentile_99 DOUBLE PRECISION,
    
    PRIMARY KEY (instance_id, metric_type, aggregation_period, period_start)
);

CREATE INDEX idx_aggregations_period ON orchestrator.metric_aggregations(aggregation_period, period_start DESC);

-- Create function to automatically aggregate metrics
CREATE OR REPLACE FUNCTION orchestrator.aggregate_metrics()
RETURNS void AS $$
DECLARE
    current_hour TIMESTAMP WITH TIME ZONE;
BEGIN
    current_hour := date_trunc('hour', NOW() - INTERVAL '1 hour');
    
    -- Aggregate hourly metrics
    INSERT INTO orchestrator.metric_aggregations (
        instance_id, metric_type, aggregation_period, period_start,
        min_value, max_value, avg_value, sum_value, count,
        percentile_50, percentile_95, percentile_99
    )
    SELECT 
        instance_id,
        metric_type,
        'hour' as aggregation_period,
        current_hour as period_start,
        MIN(value) as min_value,
        MAX(value) as max_value,
        AVG(value) as avg_value,
        SUM(value) as sum_value,
        COUNT(*) as count,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) as percentile_50,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value) as percentile_95,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY value) as percentile_99
    FROM orchestrator.instance_metrics
    WHERE timestamp >= current_hour 
    AND timestamp < current_hour + INTERVAL '1 hour'
    GROUP BY instance_id, metric_type
    ON CONFLICT (instance_id, metric_type, aggregation_period, period_start) DO NOTHING;
    
    -- Aggregate daily metrics from hourly
    IF EXTRACT(hour FROM current_hour) = 0 THEN
        INSERT INTO orchestrator.metric_aggregations (
            instance_id, metric_type, aggregation_period, period_start,
            min_value, max_value, avg_value, sum_value, count
        )
        SELECT 
            instance_id,
            metric_type,
            'day' as aggregation_period,
            date_trunc('day', current_hour - INTERVAL '1 day') as period_start,
            MIN(min_value) as min_value,
            MAX(max_value) as max_value,
            AVG(avg_value) as avg_value,
            SUM(sum_value) as sum_value,
            SUM(count) as count
        FROM orchestrator.metric_aggregations
        WHERE aggregation_period = 'hour'
        AND period_start >= date_trunc('day', current_hour - INTERVAL '1 day')
        AND period_start < date_trunc('day', current_hour)
        GROUP BY instance_id, metric_type
        ON CONFLICT (instance_id, metric_type, aggregation_period, period_start) DO NOTHING;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create view for monitoring dashboard
CREATE OR REPLACE VIEW orchestrator.monitoring_dashboard AS
SELECT 
    pi.id as instance_id,
    pi.instance_name,
    pt.display_name as persona_type_name,
    pi.azure_devops_project,
    il.current_state,
    il.last_updated as state_last_updated,
    COALESCE(
        (SELECT value FROM orchestrator.instance_metrics 
         WHERE instance_id = pi.id 
         AND metric_type = 'health_score' 
         ORDER BY timestamp DESC LIMIT 1), 
        0
    ) as current_health_score,
    COALESCE(
        (SELECT value FROM orchestrator.instance_metrics 
         WHERE instance_id = pi.id 
         AND metric_type = 'error_rate' 
         ORDER BY timestamp DESC LIMIT 1), 
        0
    ) as current_error_rate,
    COALESCE(
        (SELECT COUNT(*) FROM orchestrator.monitoring_alerts 
         WHERE instance_id = pi.id 
         AND NOT resolved), 
        0
    ) as active_alerts,
    pi.current_spend_daily,
    pi.spend_limit_daily,
    pi.current_spend_monthly,
    pi.spend_limit_monthly
FROM orchestrator.persona_instances pi
LEFT JOIN orchestrator.persona_types pt ON pi.persona_type_id = pt.id
LEFT JOIN orchestrator.instance_lifecycle il ON pi.id = il.instance_id
WHERE pi.is_active = true;

-- Grant permissions
GRANT SELECT, INSERT ON orchestrator.instance_metrics TO orchestrator_user;
GRANT SELECT, INSERT, UPDATE ON orchestrator.monitoring_alerts TO orchestrator_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON orchestrator.sla_targets TO orchestrator_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON orchestrator.monitoring_dashboards TO orchestrator_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON orchestrator.alert_rules TO orchestrator_user;
GRANT SELECT, INSERT ON orchestrator.metric_aggregations TO orchestrator_user;
GRANT SELECT ON orchestrator.monitoring_dashboard TO orchestrator_user;