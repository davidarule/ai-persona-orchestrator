-- Phase 2: Persona Instance Lifecycle Tables
-- Tables for tracking instance lifecycle states and events

-- Instance lifecycle state tracking
CREATE TABLE IF NOT EXISTS orchestrator.instance_lifecycle (
    instance_id UUID PRIMARY KEY REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    current_state VARCHAR(50) NOT NULL,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- State metadata
    error_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMP WITH TIME ZONE,
    maintenance_count INTEGER DEFAULT 0,
    last_maintenance_at TIMESTAMP WITH TIME ZONE,
    
    -- Indexes
    CONSTRAINT valid_state CHECK (current_state IN (
        'provisioning', 'initializing', 'active', 'busy', 
        'paused', 'error', 'maintenance', 'terminating', 'terminated'
    ))
);

CREATE INDEX idx_lifecycle_state ON orchestrator.instance_lifecycle(current_state);
CREATE INDEX idx_lifecycle_updated ON orchestrator.instance_lifecycle(last_updated);

-- Lifecycle event history
CREATE TABLE IF NOT EXISTS orchestrator.lifecycle_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    from_state VARCHAR(50),
    to_state VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    details JSONB,
    triggered_by VARCHAR(50) NOT NULL, -- system, user, automation
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    
    -- Indexes
    CONSTRAINT valid_from_state CHECK (from_state IS NULL OR from_state IN (
        'provisioning', 'initializing', 'active', 'busy', 
        'paused', 'error', 'maintenance', 'terminating', 'terminated'
    )),
    CONSTRAINT valid_to_state CHECK (to_state IN (
        'provisioning', 'initializing', 'active', 'busy', 
        'paused', 'error', 'maintenance', 'terminating', 'terminated'
    ))
);

CREATE INDEX idx_lifecycle_events_instance ON orchestrator.lifecycle_events(instance_id, timestamp DESC);
CREATE INDEX idx_lifecycle_events_type ON orchestrator.lifecycle_events(event_type);
CREATE INDEX idx_lifecycle_events_timestamp ON orchestrator.lifecycle_events(timestamp DESC);

-- Health check results
CREATE TABLE IF NOT EXISTS orchestrator.health_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    check_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) NOT NULL, -- healthy, warning, critical, unknown
    checks JSONB NOT NULL, -- Individual check results
    metrics JSONB, -- Performance metrics
    issues TEXT[], -- List of issues found
    recommendations TEXT[], -- Suggested actions
    
    -- Indexes
    CONSTRAINT valid_health_status CHECK (status IN ('healthy', 'warning', 'critical', 'unknown'))
);

CREATE INDEX idx_health_checks_instance ON orchestrator.health_checks(instance_id, check_time DESC);
CREATE INDEX idx_health_checks_status ON orchestrator.health_checks(status);

-- Maintenance windows
CREATE TABLE IF NOT EXISTS orchestrator.maintenance_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id UUID NOT NULL REFERENCES orchestrator.persona_instances(id) ON DELETE CASCADE,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    maintenance_type VARCHAR(100) NOT NULL,
    description TEXT,
    auto_resume BOOLEAN DEFAULT true,
    notification_sent BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(100),
    
    -- Ensure end time is after start time
    CONSTRAINT valid_maintenance_window CHECK (end_time > start_time)
);

CREATE INDEX idx_maintenance_windows_instance ON orchestrator.maintenance_windows(instance_id);
CREATE INDEX idx_maintenance_windows_time ON orchestrator.maintenance_windows(start_time, end_time);

-- Add lifecycle tracking function
CREATE OR REPLACE FUNCTION orchestrator.track_lifecycle_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Automatically update last_updated when state changes
    NEW.last_updated = NOW();
    
    -- Track error occurrences
    IF NEW.current_state = 'error' AND (OLD.current_state IS NULL OR OLD.current_state != 'error') THEN
        NEW.error_count = COALESCE(OLD.error_count, 0) + 1;
        NEW.last_error_at = NOW();
    END IF;
    
    -- Track maintenance occurrences
    IF NEW.current_state = 'maintenance' AND (OLD.current_state IS NULL OR OLD.current_state != 'maintenance') THEN
        NEW.maintenance_count = COALESCE(OLD.maintenance_count, 0) + 1;
        NEW.last_maintenance_at = NOW();
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for lifecycle tracking
CREATE TRIGGER lifecycle_tracking_trigger
BEFORE INSERT OR UPDATE ON orchestrator.instance_lifecycle
FOR EACH ROW
EXECUTE FUNCTION orchestrator.track_lifecycle_change();

-- Add function to get instance lifecycle summary
CREATE OR REPLACE FUNCTION orchestrator.get_lifecycle_summary(
    p_instance_id UUID DEFAULT NULL,
    p_days_back INTEGER DEFAULT 30
)
RETURNS TABLE (
    instance_id UUID,
    current_state VARCHAR(50),
    total_events BIGINT,
    state_distribution JSONB,
    error_count INTEGER,
    uptime_percentage NUMERIC(5,2),
    last_health_check TIMESTAMP WITH TIME ZONE,
    health_status VARCHAR(20)
) AS $$
BEGIN
    RETURN QUERY
    WITH event_summary AS (
        SELECT 
            le.instance_id,
            COUNT(*) as event_count,
            jsonb_object_agg(le.to_state, COUNT(*)) as state_counts
        FROM orchestrator.lifecycle_events le
        WHERE (p_instance_id IS NULL OR le.instance_id = p_instance_id)
        AND le.timestamp >= NOW() - INTERVAL '1 day' * p_days_back
        GROUP BY le.instance_id
    ),
    uptime_calc AS (
        SELECT 
            le.instance_id,
            SUM(
                CASE 
                    WHEN le.to_state IN ('active', 'busy') THEN 
                        EXTRACT(EPOCH FROM (
                            LEAD(le.timestamp, 1, NOW()) OVER (PARTITION BY le.instance_id ORDER BY le.timestamp) - le.timestamp
                        ))
                    ELSE 0 
                END
            ) / EXTRACT(EPOCH FROM (INTERVAL '1 day' * p_days_back)) * 100 as uptime_pct
        FROM orchestrator.lifecycle_events le
        WHERE (p_instance_id IS NULL OR le.instance_id = p_instance_id)
        AND le.timestamp >= NOW() - INTERVAL '1 day' * p_days_back
        GROUP BY le.instance_id
    ),
    latest_health AS (
        SELECT DISTINCT ON (hc.instance_id)
            hc.instance_id,
            hc.check_time,
            hc.status
        FROM orchestrator.health_checks hc
        WHERE (p_instance_id IS NULL OR hc.instance_id = p_instance_id)
        ORDER BY hc.instance_id, hc.check_time DESC
    )
    SELECT 
        il.instance_id,
        il.current_state,
        COALESCE(es.event_count, 0) as total_events,
        COALESCE(es.state_counts, '{}'::jsonb) as state_distribution,
        il.error_count,
        COALESCE(uc.uptime_pct, 0)::NUMERIC(5,2) as uptime_percentage,
        lh.check_time as last_health_check,
        lh.status as health_status
    FROM orchestrator.instance_lifecycle il
    LEFT JOIN event_summary es ON il.instance_id = es.instance_id
    LEFT JOIN uptime_calc uc ON il.instance_id = uc.instance_id
    LEFT JOIN latest_health lh ON il.instance_id = lh.instance_id
    WHERE (p_instance_id IS NULL OR il.instance_id = p_instance_id);
END;
$$ LANGUAGE plpgsql;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON orchestrator.instance_lifecycle TO orchestrator_user;
GRANT SELECT, INSERT ON orchestrator.lifecycle_events TO orchestrator_user;
GRANT SELECT, INSERT ON orchestrator.health_checks TO orchestrator_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON orchestrator.maintenance_windows TO orchestrator_user;