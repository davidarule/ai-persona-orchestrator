"""
Unit tests for Persona Instance Monitoring Service
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from collections import deque

from backend.services.persona_instance_monitoring import (
    PersonaInstanceMonitoring,
    MetricType,
    AlertType,
    AlertSeverity,
    MetricPoint,
    Alert,
    SLATarget
)
from backend.services.persona_instance_lifecycle import InstanceState, InstanceHealthStatus


class TestPersonaInstanceMonitoring:
    """Unit tests for PersonaInstanceMonitoring service"""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database manager"""
        db = AsyncMock()
        db.execute_query = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_lifecycle_service(self):
        """Create mock lifecycle service"""
        service = AsyncMock()
        service.initialize = AsyncMock()
        service.close = AsyncMock()
        service.get_instance_state = AsyncMock(return_value=InstanceState.ACTIVE)
        
        # Mock health check
        mock_health = MagicMock()
        mock_health.status = InstanceHealthStatus.HEALTHY
        mock_health.checks = {
            'instance_exists': True,
            'has_lifecycle_state': True,
            'spend_within_limits': True,
            'llm_providers_healthy': True,
            'has_recent_activity': True,
            'acceptable_error_rate': True
        }
        mock_health.issues = []
        mock_health.recommendations = []
        
        service.check_instance_health = AsyncMock(return_value=mock_health)
        return service
    
    @pytest.fixture
    def mock_spend_service(self):
        """Create mock spend tracking service"""
        service = AsyncMock()
        service.initialize = AsyncMock()
        service.close = AsyncMock()
        service.get_spend_status = AsyncMock(return_value={
            'daily_percentage': 45.0,
            'monthly_percentage': 30.0,
            'daily_exceeded': False,
            'monthly_exceeded': False,
            'daily_remaining': 55.00,
            'monthly_remaining': 1400.00
        })
        return service
    
    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM provider service"""
        service = AsyncMock()
        service.initialize = AsyncMock()
        service.close = AsyncMock()
        return service
    
    @pytest.fixture
    async def monitoring_service(self, mock_db, mock_lifecycle_service, mock_spend_service, mock_llm_service):
        """Create monitoring service with mocked dependencies"""
        service = PersonaInstanceMonitoring(mock_db)
        
        # Replace services with mocks
        service.lifecycle_service = mock_lifecycle_service
        service.spend_service = mock_spend_service
        service.llm_service = mock_llm_service
        
        # Mock database queries
        mock_db.execute_query.return_value = []
        
        await service.initialize()
        
        # Set shorter intervals for testing
        service.collection_interval = 0.1  # 100ms for faster tests
        
        return service
    
    async def test_start_stop_monitoring(self, monitoring_service):
        """Test starting and stopping instance monitoring"""
        instance_id = uuid4()
        
        # Start monitoring
        await monitoring_service.start_monitoring(instance_id)
        assert instance_id in monitoring_service._monitoring_tasks
        assert monitoring_service._monitoring_tasks[instance_id].cancelled() is False
        
        # Wait briefly for monitoring to run
        await asyncio.sleep(0.2)
        
        # Stop monitoring
        await monitoring_service.stop_monitoring(instance_id)
        assert instance_id not in monitoring_service._monitoring_tasks
    
    async def test_record_and_retrieve_metrics(self, monitoring_service):
        """Test recording and retrieving metrics"""
        instance_id = uuid4()
        
        # Record some metrics
        for i in range(10):
            monitoring_service._record_metric(
                instance_id,
                MetricType.RESPONSE_TIME,
                1.0 + i * 0.1,
                datetime.utcnow() - timedelta(minutes=10-i)
            )
        
        # Get metric summary
        summary = await monitoring_service.get_metric_summary(
            instance_id,
            MetricType.RESPONSE_TIME,
            timedelta(hours=1)
        )
        
        assert summary is not None
        assert summary.metric_type == MetricType.RESPONSE_TIME
        assert summary.sample_count == 10
        assert summary.min_value == 1.0
        assert summary.max_value == 1.9
        assert 1.4 < summary.average < 1.5
        assert summary.current_value == 1.9
    
    async def test_health_score_calculation(self, monitoring_service):
        """Test health score calculation"""
        # Test healthy instance
        health = MagicMock()
        health.status = InstanceHealthStatus.HEALTHY
        health.checks = {
            'check1': True,
            'check2': True,
            'check3': True
        }
        health.issues = []
        
        score = monitoring_service._calculate_health_score(health)
        assert score == 100.0
        
        # Test warning instance
        health.status = InstanceHealthStatus.WARNING
        health.checks = {
            'check1': True,
            'check2': False,
            'check3': True
        }
        health.issues = ["Issue 1", "Issue 2"]
        
        score = monitoring_service._calculate_health_score(health)
        assert 60 < score < 80  # Should be reduced but not critical
        
        # Test critical instance
        health.status = InstanceHealthStatus.CRITICAL
        health.checks = {
            'check1': False,
            'check2': False,
            'check3': False
        }
        health.issues = ["Critical issue"]
        
        score = monitoring_service._calculate_health_score(health)
        assert score < 30  # Should be very low
    
    async def test_metric_trend_calculation(self, monitoring_service):
        """Test trend calculation for metrics"""
        instance_id = uuid4()
        
        # Increasing trend
        for i in range(10):
            monitoring_service._record_metric(
                instance_id,
                MetricType.TOKEN_USAGE,
                100 + i * 10
            )
        
        summary = await monitoring_service.get_metric_summary(
            instance_id,
            MetricType.TOKEN_USAGE
        )
        assert summary.trend == "increasing"
        
        # Decreasing trend
        instance_id2 = uuid4()
        for i in range(10):
            monitoring_service._record_metric(
                instance_id2,
                MetricType.ERROR_RATE,
                0.1 - i * 0.01
            )
        
        summary2 = await monitoring_service.get_metric_summary(
            instance_id2,
            MetricType.ERROR_RATE
        )
        assert summary2.trend == "decreasing"
        
        # Stable trend
        instance_id3 = uuid4()
        for i in range(10):
            monitoring_service._record_metric(
                instance_id3,
                MetricType.COST_PER_TASK,
                0.05 + (0.001 if i % 2 == 0 else -0.001)
            )
        
        summary3 = await monitoring_service.get_metric_summary(
            instance_id3,
            MetricType.COST_PER_TASK
        )
        assert summary3.trend == "stable"
    
    async def test_anomaly_detection(self, monitoring_service):
        """Test anomaly detection in metrics"""
        instance_id = uuid4()
        
        # Create normal pattern
        for i in range(20):
            monitoring_service._record_metric(
                instance_id,
                MetricType.RESPONSE_TIME,
                1.0 + (0.1 if i % 2 == 0 else -0.1)
            )
        
        # Add anomaly
        monitoring_service._record_metric(
            instance_id,
            MetricType.RESPONSE_TIME,
            5.0  # Anomalous value
        )
        
        # Run anomaly detection
        await monitoring_service._detect_anomalies(instance_id)
        
        # Should have created an alert
        alerts = monitoring_service._alerts[instance_id]
        anomaly_alerts = [a for a in alerts if a.alert_type == AlertType.ANOMALY_DETECTED]
        assert len(anomaly_alerts) > 0
        assert anomaly_alerts[0].details['z_score'] > 3
    
    async def test_alert_creation_and_deduplication(self, monitoring_service):
        """Test alert creation and deduplication"""
        instance_id = uuid4()
        
        # Create first alert
        await monitoring_service._create_alert(
            instance_id,
            AlertType.HIGH_ERROR_RATE,
            AlertSeverity.ERROR,
            "High error rate detected",
            {"error_rate": 0.15}
        )
        
        assert len(monitoring_service._alerts[instance_id]) == 1
        
        # Try to create duplicate alert (should be ignored)
        await monitoring_service._create_alert(
            instance_id,
            AlertType.HIGH_ERROR_RATE,
            AlertSeverity.ERROR,
            "High error rate detected",
            {"error_rate": 0.16}
        )
        
        # Should still have only one alert
        assert len(monitoring_service._alerts[instance_id]) == 1
    
    async def test_sla_compliance_checking(self, monitoring_service):
        """Test SLA compliance checking"""
        instance_id = uuid4()
        
        # Set SLA targets
        targets = [
            SLATarget(
                metric_type=MetricType.RESPONSE_TIME,
                target_value=2.0,
                comparison="less_than",
                measurement_window=timedelta(minutes=5),
                violation_threshold=3
            ),
            SLATarget(
                metric_type=MetricType.AVAILABILITY,
                target_value=95.0,
                comparison="greater_than",
                measurement_window=timedelta(hours=1),
                violation_threshold=1
            )
        ]
        
        await monitoring_service.set_sla_targets(instance_id, targets)
        
        # Record metrics that violate SLA
        for i in range(10):
            monitoring_service._record_metric(
                instance_id,
                MetricType.RESPONSE_TIME,
                3.0  # Above target of 2.0
            )
            monitoring_service._record_metric(
                instance_id,
                MetricType.AVAILABILITY,
                90.0  # Below target of 95.0
            )
        
        # Check SLA compliance
        await monitoring_service._check_sla_compliance(instance_id)
        
        # Should have SLA violation alerts
        alerts = await monitoring_service.get_active_alerts(instance_id)
        sla_alerts = [a for a in alerts if a.alert_type == AlertType.SLA_VIOLATION]
        assert len(sla_alerts) >= 1
    
    async def test_monitoring_dashboard_data(self, monitoring_service, mock_db):
        """Test monitoring dashboard data generation"""
        instance_id = uuid4()
        
        # Record various metrics
        for metric_type in [MetricType.RESPONSE_TIME, MetricType.ERROR_RATE, MetricType.HEALTH_SCORE]:
            for i in range(5):
                monitoring_service._record_metric(
                    instance_id,
                    metric_type,
                    i * 0.1
                )
        
        # Create some alerts
        await monitoring_service._create_alert(
            instance_id,
            AlertType.PERFORMANCE_DEGRADATION,
            AlertSeverity.WARNING,
            "Performance degraded",
            {}
        )
        
        # Get dashboard data
        dashboard = await monitoring_service.get_monitoring_dashboard(instance_id)
        
        assert dashboard['instance_id'] == str(instance_id)
        assert dashboard['current_state'] == 'active'
        assert dashboard['health_status'] == 'healthy'
        assert dashboard['health_score'] == 100.0
        assert len(dashboard['metrics']) > 0
        assert dashboard['active_alerts'] == 1
        assert len(dashboard['alerts']) == 1
        assert 'spend' in dashboard
        assert 'sla_compliance' in dashboard
    
    async def test_alert_resolution(self, monitoring_service):
        """Test alert resolution"""
        instance_id = uuid4()
        
        # Create alert
        await monitoring_service._create_alert(
            instance_id,
            AlertType.HIGH_ERROR_RATE,
            AlertSeverity.ERROR,
            "High error rate",
            {}
        )
        
        alerts = await monitoring_service.get_active_alerts(instance_id)
        assert len(alerts) == 1
        
        alert_id = alerts[0].id
        
        # Resolve alert
        await monitoring_service.resolve_alert(alert_id)
        
        # Check resolved
        active_alerts = await monitoring_service.get_active_alerts(instance_id)
        assert len(active_alerts) == 0
        
        # Check alert is marked resolved
        all_alerts = monitoring_service._alerts[instance_id]
        assert all_alerts[0].resolved is True
        assert all_alerts[0].resolved_at is not None
    
    async def test_metric_persistence_with_error_handling(self, monitoring_service, mock_db):
        """Test metric persistence with error handling"""
        instance_id = uuid4()
        
        # Record metrics
        monitoring_service._record_metric(
            instance_id,
            MetricType.RESPONSE_TIME,
            1.5
        )
        
        # Mock database error
        mock_db.execute_query.side_effect = Exception("Database error")
        
        # Should handle error gracefully
        await monitoring_service._persist_instance_metrics(instance_id)
        
        # Verify error was logged but didn't crash
        assert mock_db.execute_query.called
    
    async def test_performance_metrics_calculation(self, monitoring_service, mock_db):
        """Test performance metrics calculation from database"""
        instance_id = uuid4()
        
        # Mock performance data
        mock_db.execute_query.return_value = {
            'avg_response_time': 1.5,
            'avg_tokens': 150,
            'avg_cost': 0.05,
            'error_rate': 5.0,
            'total_requests': 100
        }
        
        metrics = await monitoring_service._get_performance_metrics(instance_id)
        
        assert metrics is not None
        assert metrics['avg_response_time'] == 1.5
        assert metrics['avg_tokens'] == 150
        assert metrics['avg_cost'] == 0.05
        assert metrics['error_rate'] == 0.05  # Converted from percentage
        assert metrics['total_requests'] == 100
    
    async def test_availability_calculation(self, monitoring_service, mock_db):
        """Test availability percentage calculation"""
        instance_id = uuid4()
        
        # Mock availability data
        mock_db.execute_query.return_value = {
            'active_time': 3600,  # 1 hour active
            'total_time': 7200    # 2 hours total
        }
        
        availability = await monitoring_service._calculate_availability(instance_id)
        
        assert availability == 50.0  # 50% availability
    
    async def test_metric_collection_with_full_cycle(self, monitoring_service, mock_db):
        """Test full metric collection cycle"""
        instance_id = uuid4()
        
        # Mock all required data
        mock_db.execute_query.side_effect = [
            # Performance metrics
            {
                'avg_response_time': 1.2,
                'avg_tokens': 100,
                'avg_cost': 0.03,
                'error_rate': 2.0,
                'total_requests': 50
            },
            # Availability
            {
                'active_time': 5400,  # 1.5 hours
                'total_time': 7200    # 2 hours
            },
            # State duration
            {
                'timestamp': datetime.utcnow() - timedelta(minutes=30)
            }
        ]
        
        # Run collection
        await monitoring_service._collect_instance_metrics(instance_id)
        
        # Verify metrics were recorded
        metrics = monitoring_service._metrics[instance_id]
        assert len(metrics[MetricType.HEALTH_SCORE]) > 0
        assert len(metrics[MetricType.RESPONSE_TIME]) > 0
        assert len(metrics[MetricType.ERROR_RATE]) > 0
        assert len(metrics[MetricType.AVAILABILITY]) > 0
        assert len(metrics[MetricType.STATE_DURATION]) > 0