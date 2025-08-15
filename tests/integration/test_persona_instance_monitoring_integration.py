"""
Integration tests for Persona Instance Monitoring Service
Tests real database operations and service interactions
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal

from backend.services.persona_instance_monitoring import (
    PersonaInstanceMonitoring,
    MetricType,
    AlertType,
    AlertSeverity,
    SLATarget
)
from backend.services.persona_instance_lifecycle import PersonaInstanceLifecycle, InstanceState
from backend.services.spend_tracking_service import SpendTrackingService
from backend.services.persona_instance_service import PersonaInstanceService
from backend.models.persona_instance import PersonaInstanceCreate, LLMProvider, LLMModel
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.integration
@pytest.mark.asyncio
class TestPersonaInstanceMonitoringIntegration:
    """Integration tests for monitoring with real services"""
    
    @pytest.fixture
    async def test_persona_type(self, db):
        """Create test persona type"""
        repo = PersonaTypeRepository(db)
        
        persona_type = await repo.create(PersonaTypeCreate(
            type_name=f"monitor-test-{uuid4().hex[:8]}",
            display_name="Monitor Test Persona",
            category=PersonaCategory.DEVELOPMENT,
            description="Test persona for monitoring",
            base_workflow_id="wf0"
        ))
        
        yield persona_type
        
        # Cleanup
        await db.execute_query(
            "DELETE FROM orchestrator.persona_types WHERE id = $1",
            persona_type.id
        )
    
    @pytest.fixture
    async def test_instance(self, db, test_persona_type, azure_devops_config):
        """Create test persona instance"""
        service = PersonaInstanceService(db)
        
        instance = await service.create_instance(PersonaInstanceCreate(
            instance_name=f"monitor-instance-{uuid4().hex[:8]}",
            persona_type_id=test_persona_type.id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="MonitoringTest",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ],
            spend_limit_daily=Decimal("50.00"),
            spend_limit_monthly=Decimal("1000.00")
        ))
        
        yield instance
        
        # Cleanup
        await service.delete_instance(instance.id)
    
    @pytest.fixture
    async def services(self, db):
        """Create all required services"""
        monitoring = PersonaInstanceMonitoring(db)
        lifecycle = PersonaInstanceLifecycle(db)
        spend = SpendTrackingService(db)
        
        await monitoring.initialize()
        await lifecycle.initialize()
        await spend.initialize()
        
        yield {
            "monitoring": monitoring,
            "lifecycle": lifecycle,
            "spend": spend
        }
        
        await monitoring.close()
        await lifecycle.close()
        await spend.close()
    
    async def test_monitoring_with_lifecycle_integration(self, services, test_instance):
        """Test monitoring integration with lifecycle state changes"""
        monitoring = services["monitoring"]
        lifecycle = services["lifecycle"]
        
        # Provision instance
        await lifecycle.provision_instance(test_instance.id)
        
        # Start monitoring
        await monitoring.start_monitoring(test_instance.id)
        
        # Let monitoring collect initial metrics
        await asyncio.sleep(0.5)
        
        # Verify initial health score
        health_summary = await monitoring.get_metric_summary(
            test_instance.id,
            MetricType.HEALTH_SCORE
        )
        assert health_summary is not None
        assert health_summary.current_value == 100.0  # Healthy initial state
        
        # Transition through states
        await lifecycle.activate_instance(test_instance.id)
        await asyncio.sleep(0.5)
        
        # Check state duration metric
        state_summary = await monitoring.get_metric_summary(
            test_instance.id,
            MetricType.STATE_DURATION
        )
        assert state_summary is not None
        assert state_summary.current_value > 0
        
        # Stop monitoring
        await monitoring.stop_monitoring(test_instance.id)
    
    async def test_alert_creation_and_persistence(self, services, test_instance, db):
        """Test alert creation and database persistence"""
        monitoring = services["monitoring"]
        
        # Start monitoring
        await monitoring.start_monitoring(test_instance.id)
        
        # Record metrics that will trigger alerts
        for i in range(10):
            monitoring._record_metric(
                test_instance.id,
                MetricType.ERROR_RATE,
                0.15  # Above threshold of 0.1
            )
        
        # Trigger alert check
        await monitoring._check_metric_alerts(test_instance.id)
        
        # Verify alert was created
        alerts = await monitoring.get_active_alerts(test_instance.id)
        assert len(alerts) > 0
        assert any(a.alert_type == AlertType.HIGH_ERROR_RATE for a in alerts)
        
        # Verify alert in database
        result = await db.execute_query(
            """
            SELECT COUNT(*) as count
            FROM orchestrator.monitoring_alerts
            WHERE instance_id = $1
            AND alert_type = 'high_error_rate'
            AND NOT resolved
            """,
            test_instance.id,
            fetch_one=True
        )
        assert result["count"] >= 1
        
        # Resolve alert
        alert = alerts[0]
        await monitoring.resolve_alert(alert.id)
        
        # Verify resolution
        active_alerts = await monitoring.get_active_alerts(test_instance.id)
        assert len(active_alerts) == 0
        
        # Stop monitoring
        await monitoring.stop_monitoring(test_instance.id)
    
    async def test_sla_compliance_monitoring(self, services, test_instance):
        """Test SLA target monitoring and violations"""
        monitoring = services["monitoring"]
        
        # Set SLA targets
        sla_targets = [
            SLATarget(
                metric_type=MetricType.RESPONSE_TIME,
                target_value=2.0,  # 2 seconds max
                comparison="less_than",
                measurement_window=timedelta(minutes=5),
                violation_threshold=3
            ),
            SLATarget(
                metric_type=MetricType.ERROR_RATE,
                target_value=0.05,  # 5% max error rate
                comparison="less_than",
                measurement_window=timedelta(minutes=5),
                violation_threshold=1
            )
        ]
        
        await monitoring.set_sla_targets(test_instance.id, sla_targets)
        
        # Start monitoring
        await monitoring.start_monitoring(test_instance.id)
        
        # Record metrics that violate SLA
        for i in range(10):
            monitoring._record_metric(
                test_instance.id,
                MetricType.RESPONSE_TIME,
                3.0  # Above target of 2.0
            )
            monitoring._record_metric(
                test_instance.id,
                MetricType.ERROR_RATE,
                0.08  # Above target of 0.05
            )
        
        # Check SLA compliance
        await monitoring._check_sla_compliance(test_instance.id)
        
        # Verify SLA violation alerts
        alerts = await monitoring.get_active_alerts(test_instance.id)
        sla_alerts = [a for a in alerts if a.alert_type == AlertType.SLA_VIOLATION]
        assert len(sla_alerts) >= 1
        
        # Get compliance summary
        dashboard = await monitoring.get_monitoring_dashboard(test_instance.id)
        assert dashboard["sla_compliance"]["has_sla"] is True
        assert dashboard["sla_compliance"]["compliance_rate"] == 0.0  # Both SLAs violated
        
        # Stop monitoring
        await monitoring.stop_monitoring(test_instance.id)
    
    async def test_metric_persistence_and_retrieval(self, services, test_instance, db):
        """Test metric persistence to database"""
        monitoring = services["monitoring"]
        
        # Start monitoring
        await monitoring.start_monitoring(test_instance.id)
        
        # Record various metrics
        metric_data = [
            (MetricType.RESPONSE_TIME, [1.2, 1.5, 1.8, 2.1, 1.9]),
            (MetricType.TOKEN_USAGE, [100, 150, 200, 175, 190]),
            (MetricType.COST_PER_TASK, [0.02, 0.03, 0.04, 0.03, 0.035])
        ]
        
        for metric_type, values in metric_data:
            for value in values:
                monitoring._record_metric(
                    test_instance.id,
                    metric_type,
                    value
                )
                await asyncio.sleep(0.1)
        
        # Persist metrics
        await monitoring._persist_instance_metrics(test_instance.id)
        
        # Verify metrics in database
        for metric_type, expected_values in metric_data:
            result = await db.execute_query(
                """
                SELECT COUNT(*) as count, AVG(value) as avg_value
                FROM orchestrator.instance_metrics
                WHERE instance_id = $1
                AND metric_type = $2
                """,
                test_instance.id,
                metric_type.value,
                fetch_one=True
            )
            
            assert result["count"] == len(expected_values)
            assert abs(result["avg_value"] - sum(expected_values) / len(expected_values)) < 0.01
        
        # Stop monitoring
        await monitoring.stop_monitoring(test_instance.id)
    
    async def test_anomaly_detection_integration(self, services, test_instance):
        """Test anomaly detection with real metrics"""
        monitoring = services["monitoring"]
        
        # Start monitoring
        await monitoring.start_monitoring(test_instance.id)
        
        # Create normal baseline
        for i in range(20):
            monitoring._record_metric(
                test_instance.id,
                MetricType.RESPONSE_TIME,
                1.0 + (i % 3) * 0.1  # Values: 1.0, 1.1, 1.2, repeating
            )
        
        # Add anomalous values
        for _ in range(3):
            monitoring._record_metric(
                test_instance.id,
                MetricType.RESPONSE_TIME,
                5.0  # Significantly higher than baseline
            )
        
        # Run anomaly detection
        await monitoring._detect_anomalies(test_instance.id)
        
        # Check for anomaly alerts
        alerts = await monitoring.get_active_alerts(test_instance.id)
        anomaly_alerts = [a for a in alerts if a.alert_type == AlertType.ANOMALY_DETECTED]
        
        assert len(anomaly_alerts) > 0
        assert anomaly_alerts[0].details["z_score"] > 3
        
        # Stop monitoring
        await monitoring.stop_monitoring(test_instance.id)
    
    async def test_dashboard_data_aggregation(self, services, test_instance):
        """Test comprehensive dashboard data generation"""
        monitoring = services["monitoring"]
        lifecycle = services["lifecycle"]
        
        # Provision and activate instance
        await lifecycle.provision_instance(test_instance.id)
        await lifecycle.activate_instance(test_instance.id)
        
        # Start monitoring
        await monitoring.start_monitoring(test_instance.id)
        
        # Generate various metrics
        metrics_to_record = [
            (MetricType.HEALTH_SCORE, 95.0),
            (MetricType.RESPONSE_TIME, 1.5),
            (MetricType.ERROR_RATE, 0.02),
            (MetricType.TOKEN_USAGE, 150),
            (MetricType.COST_PER_TASK, 0.03),
            (MetricType.AVAILABILITY, 98.5)
        ]
        
        for metric_type, value in metrics_to_record:
            monitoring._record_metric(test_instance.id, metric_type, value)
        
        # Create an alert
        await monitoring._create_alert(
            test_instance.id,
            AlertType.PERFORMANCE_DEGRADATION,
            AlertSeverity.WARNING,
            "Test performance alert",
            {"test": True}
        )
        
        # Get dashboard data
        dashboard = await monitoring.get_monitoring_dashboard(test_instance.id)
        
        # Verify dashboard structure
        assert dashboard["instance_id"] == str(test_instance.id)
        assert dashboard["current_state"] == "active"
        assert dashboard["health_status"] == "healthy"
        assert dashboard["health_score"] == 100.0  # From lifecycle health check
        
        # Verify metrics
        assert len(dashboard["metrics"]) > 0
        assert MetricType.HEALTH_SCORE.value in dashboard["metrics"]
        
        # Verify alerts
        assert dashboard["active_alerts"] == 1
        assert len(dashboard["alerts"]) == 1
        assert dashboard["alerts"][0]["type"] == AlertType.PERFORMANCE_DEGRADATION.value
        
        # Stop monitoring
        await monitoring.stop_monitoring(test_instance.id)
    
    async def test_concurrent_monitoring_multiple_instances(self, services, test_persona_type, azure_devops_config, db):
        """Test monitoring multiple instances concurrently"""
        monitoring = services["monitoring"]
        instance_service = PersonaInstanceService(db)
        
        # Create multiple instances
        instances = []
        for i in range(3):
            instance = await instance_service.create_instance(PersonaInstanceCreate(
                instance_name=f"concurrent-monitor-{i}-{uuid4().hex[:8]}",
                persona_type_id=test_persona_type.id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project="ConcurrentMonitorTest",
                llm_providers=[
                    LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name="gpt-3.5-turbo",
                        api_key_env_var="OPENAI_API_KEY"
                    )
                ],
                spend_limit_daily=Decimal("50.00"),
                spend_limit_monthly=Decimal("1000.00")
            ))
            instances.append(instance)
        
        # Start monitoring all instances
        for instance in instances:
            await monitoring.start_monitoring(instance.id)
        
        # Record different metrics for each instance
        for i, instance in enumerate(instances):
            base_response_time = 1.0 + i * 0.5
            for j in range(5):
                monitoring._record_metric(
                    instance.id,
                    MetricType.RESPONSE_TIME,
                    base_response_time + j * 0.1
                )
        
        # Wait for monitoring cycles
        await asyncio.sleep(1)
        
        # Verify each instance has its own metrics
        for i, instance in enumerate(instances):
            summary = await monitoring.get_metric_summary(
                instance.id,
                MetricType.RESPONSE_TIME
            )
            
            expected_base = 1.0 + i * 0.5
            assert abs(summary.min_value - expected_base) < 0.01
            assert summary.sample_count == 5
        
        # Stop all monitoring
        for instance in instances:
            await monitoring.stop_monitoring(instance.id)
        
        # Cleanup
        for instance in instances:
            await instance_service.delete_instance(instance.id)
    
    async def test_metric_aggregation_function(self, services, test_instance, db):
        """Test database metric aggregation function"""
        monitoring = services["monitoring"]
        
        # Record metrics over time
        base_time = datetime.utcnow() - timedelta(hours=2)
        
        # Insert historical metrics directly
        for i in range(120):  # 2 hours of data, 1 per minute
            timestamp = base_time + timedelta(minutes=i)
            value = 1.0 + (i % 10) * 0.1  # Varying values
            
            await db.execute_query(
                """
                INSERT INTO orchestrator.instance_metrics
                (instance_id, metric_type, timestamp, value)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT DO NOTHING
                """,
                test_instance.id,
                MetricType.RESPONSE_TIME.value,
                timestamp,
                value
            )
        
        # Run aggregation function
        await db.execute_query("SELECT orchestrator.aggregate_metrics()")
        
        # Check aggregated data
        result = await db.execute_query(
            """
            SELECT COUNT(*) as count,
                   AVG(avg_value) as overall_avg
            FROM orchestrator.metric_aggregations
            WHERE instance_id = $1
            AND metric_type = $2
            AND aggregation_period = 'hour'
            """,
            test_instance.id,
            MetricType.RESPONSE_TIME.value,
            fetch_one=True
        )
        
        assert result["count"] >= 1  # At least one hour aggregated
        assert result["overall_avg"] is not None