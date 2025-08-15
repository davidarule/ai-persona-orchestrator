-- Fix monitoring dashboard view
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
GRANT SELECT ON orchestrator.monitoring_dashboard TO orchestrator_user;