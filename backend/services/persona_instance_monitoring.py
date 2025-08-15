"""
Persona Instance Monitoring Service

Provides comprehensive monitoring, metrics collection, and alerting for persona instances
including performance tracking, anomaly detection, and operational insights.
"""

import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import json
import logging
import statistics
from uuid import UUID

from backend.services.database import DatabaseManager
from backend.services.persona_instance_lifecycle import PersonaInstanceLifecycle, InstanceState, InstanceHealthStatus
from backend.services.spend_tracking_service import SpendTrackingService
from backend.services.llm_provider_service import LLMProviderService
from backend.models.persona_instance import PersonaInstance


# Configure logging
logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics to track"""
    RESPONSE_TIME = "response_time"
    TOKEN_USAGE = "token_usage"
    ERROR_RATE = "error_rate"
    COST_PER_TASK = "cost_per_task"
    AVAILABILITY = "availability"
    TASK_COMPLETION = "task_completion"
    STATE_DURATION = "state_duration"
    HEALTH_SCORE = "health_score"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of monitoring alerts"""
    HIGH_ERROR_RATE = "high_error_rate"
    SPEND_THRESHOLD = "spend_threshold"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    INSTANCE_UNHEALTHY = "instance_unhealthy"
    PROLONGED_BUSY_STATE = "prolonged_busy_state"
    ANOMALY_DETECTED = "anomaly_detected"
    SLA_VIOLATION = "sla_violation"


@dataclass
class MetricPoint:
    """Single metric data point"""
    timestamp: datetime
    value: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MetricSummary:
    """Summary statistics for a metric"""
    metric_type: MetricType
    current_value: float
    average: float
    min_value: float
    max_value: float
    std_deviation: float
    percentile_50: float
    percentile_95: float
    percentile_99: float
    trend: str  # increasing, decreasing, stable
    sample_count: int
    time_window: timedelta


@dataclass
class Alert:
    """Monitoring alert"""
    id: UUID
    instance_id: UUID
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    details: Dict[str, Any]
    created_at: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    
@dataclass
class SLATarget:
    """Service Level Agreement target"""
    metric_type: MetricType
    target_value: float
    comparison: str  # less_than, greater_than, equal_to
    measurement_window: timedelta
    violation_threshold: int  # Number of violations before alert


class PersonaInstanceMonitoring:
    """
    Comprehensive monitoring for persona instances
    
    Features:
    - Real-time metrics collection
    - Performance tracking
    - Anomaly detection
    - SLA monitoring
    - Alert management
    - Historical analysis
    - Predictive insights
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.lifecycle_service = PersonaInstanceLifecycle(db_manager)
        self.spend_service = SpendTrackingService(db_manager)
        self.llm_service = LLMProviderService(db_manager)
        
        # Metrics storage (in-memory with periodic persistence)
        self._metrics: Dict[UUID, Dict[MetricType, deque]] = defaultdict(lambda: defaultdict(lambda: deque(maxlen=1000)))
        
        # Active alerts
        self._alerts: Dict[UUID, List[Alert]] = defaultdict(list)
        
        # SLA targets
        self._sla_targets: Dict[UUID, List[SLATarget]] = {}
        
        # Monitoring configuration
        self.collection_interval = 60  # seconds
        self.retention_period = timedelta(days=30)
        
        # Alert thresholds
        self.alert_thresholds = {
            AlertType.HIGH_ERROR_RATE: 0.1,  # 10% error rate
            AlertType.SPEND_THRESHOLD: 0.9,  # 90% of limit
            AlertType.PERFORMANCE_DEGRADATION: 2.0,  # 2x slower than baseline
            AlertType.PROLONGED_BUSY_STATE: timedelta(hours=1)
        }
        
        # Background tasks
        self._monitoring_tasks: Dict[UUID, asyncio.Task] = {}
        
    async def initialize(self):
        """Initialize monitoring service"""
        await self.lifecycle_service.initialize()
        await self.spend_service.initialize()
        await self.llm_service.initialize()
        
        # Load historical metrics
        await self._load_historical_metrics()
        
        # Start background monitoring
        asyncio.create_task(self._periodic_persistence())
        
    async def close(self):
        """Clean up resources"""
        # Cancel monitoring tasks
        for task in self._monitoring_tasks.values():
            task.cancel()
        
        # Persist final metrics
        await self._persist_metrics()
        
        await self.lifecycle_service.close()
        await self.spend_service.close()
        await self.llm_service.close()
    
    async def start_monitoring(self, instance_id: UUID):
        """Start monitoring a specific instance"""
        if instance_id in self._monitoring_tasks:
            logger.warning(f"Monitoring already active for instance {instance_id}")
            return
        
        # Create monitoring task
        task = asyncio.create_task(self._monitor_instance(instance_id))
        self._monitoring_tasks[instance_id] = task
        
        logger.info(f"Started monitoring for instance {instance_id}")
    
    async def stop_monitoring(self, instance_id: UUID):
        """Stop monitoring a specific instance"""
        if instance_id in self._monitoring_tasks:
            self._monitoring_tasks[instance_id].cancel()
            del self._monitoring_tasks[instance_id]
            
            # Persist final metrics
            await self._persist_instance_metrics(instance_id)
            
            logger.info(f"Stopped monitoring for instance {instance_id}")
    
    async def _monitor_instance(self, instance_id: UUID):
        """Background task to monitor a single instance"""
        while True:
            try:
                # Collect metrics
                await self._collect_instance_metrics(instance_id)
                
                # Check for anomalies
                await self._detect_anomalies(instance_id)
                
                # Check SLA compliance
                await self._check_sla_compliance(instance_id)
                
                # Wait for next collection interval
                await asyncio.sleep(self.collection_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring instance {instance_id}: {e}")
                await asyncio.sleep(self.collection_interval)
    
    async def _collect_instance_metrics(self, instance_id: UUID):
        """Collect current metrics for an instance"""
        timestamp = datetime.utcnow()
        
        # Get instance state
        state = await self.lifecycle_service.get_instance_state(instance_id)
        if not state:
            return
        
        # Get health status
        health = await self.lifecycle_service.check_instance_health(instance_id)
        
        # Record health score (0-100)
        health_score = self._calculate_health_score(health)
        self._record_metric(instance_id, MetricType.HEALTH_SCORE, health_score, timestamp)
        
        # Get performance metrics from recent tasks
        perf_metrics = await self._get_performance_metrics(instance_id)
        if perf_metrics:
            self._record_metric(instance_id, MetricType.RESPONSE_TIME, perf_metrics['avg_response_time'], timestamp)
            self._record_metric(instance_id, MetricType.TOKEN_USAGE, perf_metrics['avg_tokens'], timestamp)
            self._record_metric(instance_id, MetricType.ERROR_RATE, perf_metrics['error_rate'], timestamp)
            self._record_metric(instance_id, MetricType.COST_PER_TASK, perf_metrics['avg_cost'], timestamp)
        
        # Calculate availability (percentage of time in active/busy states)
        availability = await self._calculate_availability(instance_id)
        self._record_metric(instance_id, MetricType.AVAILABILITY, availability, timestamp)
        
        # Track state duration
        state_duration = await self._get_state_duration(instance_id, state)
        self._record_metric(
            instance_id, 
            MetricType.STATE_DURATION, 
            state_duration.total_seconds(),
            timestamp,
            {"state": state.value}
        )
        
        # Check for alerts
        await self._check_metric_alerts(instance_id)
    
    def _calculate_health_score(self, health: Any) -> float:
        """Calculate overall health score from health check"""
        score = 100.0
        
        # Map health status to base score
        status_scores = {
            InstanceHealthStatus.HEALTHY: 100,
            InstanceHealthStatus.WARNING: 75,
            InstanceHealthStatus.CRITICAL: 25,
            InstanceHealthStatus.UNKNOWN: 50
        }
        
        base_score = status_scores.get(health.status, 50)
        
        # Adjust based on specific checks
        total_checks = len(health.checks)
        passed_checks = sum(1 for check in health.checks.values() if check)
        check_ratio = passed_checks / total_checks if total_checks > 0 else 0
        
        # Weighted score
        score = base_score * 0.6 + (check_ratio * 100) * 0.4
        
        # Penalties for issues
        score -= len(health.issues) * 5
        
        return max(0, min(100, score))
    
    async def _get_performance_metrics(self, instance_id: UUID) -> Optional[Dict[str, float]]:
        """Get performance metrics from recent LLM usage"""
        query = """
        SELECT 
            AVG(latency) as avg_response_time,
            AVG(input_tokens + output_tokens) as avg_tokens,
            AVG(cost) as avg_cost,
            COUNT(*) FILTER (WHERE success = false) * 100.0 / COUNT(*) as error_rate,
            COUNT(*) as total_requests
        FROM orchestrator.llm_usage_logs
        WHERE instance_id = $1
        AND created_at >= NOW() - INTERVAL '5 minutes'
        """
        
        result = await self.db.execute_query(query, str(instance_id), fetch_one=True)
        
        if result and result['total_requests'] > 0:
            return {
                'avg_response_time': float(result['avg_response_time'] or 0),
                'avg_tokens': float(result['avg_tokens'] or 0),
                'avg_cost': float(result['avg_cost'] or 0),
                'error_rate': float(result['error_rate'] or 0) / 100,
                'total_requests': result['total_requests']
            }
        
        return None
    
    async def _calculate_availability(self, instance_id: UUID) -> float:
        """Calculate instance availability percentage"""
        query = """
        WITH state_durations AS (
            SELECT 
                to_state,
                SUM(EXTRACT(EPOCH FROM (
                    LEAD(timestamp, 1, NOW()) OVER (ORDER BY timestamp) - timestamp
                ))) as duration_seconds
            FROM orchestrator.lifecycle_events
            WHERE instance_id = $1
            AND timestamp >= NOW() - INTERVAL '24 hours'
            GROUP BY to_state
        )
        SELECT 
            SUM(CASE WHEN to_state IN ('active', 'busy') THEN duration_seconds ELSE 0 END) as active_time,
            SUM(duration_seconds) as total_time
        FROM state_durations
        """
        
        result = await self.db.execute_query(query, instance_id, fetch_one=True)
        
        if result and result['total_time'] and result['total_time'] > 0:
            return (result['active_time'] or 0) / result['total_time'] * 100
        
        return 0.0
    
    async def _get_state_duration(self, instance_id: UUID, current_state: InstanceState) -> timedelta:
        """Get how long instance has been in current state"""
        query = """
        SELECT timestamp
        FROM orchestrator.lifecycle_events
        WHERE instance_id = $1
        AND to_state = $2
        ORDER BY timestamp DESC
        LIMIT 1
        """
        
        result = await self.db.execute_query(
            query, 
            instance_id, 
            current_state.value,
            fetch_one=True
        )
        
        if result and result['timestamp']:
            return datetime.utcnow() - result['timestamp']
        
        return timedelta(0)
    
    def _record_metric(
        self, 
        instance_id: UUID, 
        metric_type: MetricType, 
        value: float,
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record a metric data point"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        point = MetricPoint(
            timestamp=timestamp,
            value=value,
            metadata=metadata
        )
        
        self._metrics[instance_id][metric_type].append(point)
    
    async def get_metric_summary(
        self,
        instance_id: UUID,
        metric_type: MetricType,
        time_window: Optional[timedelta] = None
    ) -> Optional[MetricSummary]:
        """Get summary statistics for a metric"""
        if time_window is None:
            time_window = timedelta(hours=1)
        
        cutoff_time = datetime.utcnow() - time_window
        
        # Get data points within time window
        points = [
            p for p in self._metrics[instance_id][metric_type]
            if p.timestamp >= cutoff_time
        ]
        
        if not points:
            return None
        
        values = [p.value for p in points]
        
        # Calculate statistics
        summary = MetricSummary(
            metric_type=metric_type,
            current_value=values[-1],
            average=statistics.mean(values),
            min_value=min(values),
            max_value=max(values),
            std_deviation=statistics.stdev(values) if len(values) > 1 else 0,
            percentile_50=statistics.median(values),
            percentile_95=self._percentile(values, 0.95),
            percentile_99=self._percentile(values, 0.99),
            trend=self._calculate_trend(values),
            sample_count=len(values),
            time_window=time_window
        )
        
        return summary
    
    def _percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile value"""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile)
        return sorted_values[min(index, len(sorted_values) - 1)]
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction"""
        if len(values) < 3:
            return "stable"
        
        # Compare recent average to older average
        mid_point = len(values) // 2
        older_avg = statistics.mean(values[:mid_point])
        newer_avg = statistics.mean(values[mid_point:])
        
        change_ratio = (newer_avg - older_avg) / older_avg if older_avg != 0 else 0
        
        if change_ratio > 0.1:
            return "increasing"
        elif change_ratio < -0.1:
            return "decreasing"
        else:
            return "stable"
    
    async def _detect_anomalies(self, instance_id: UUID):
        """Detect anomalies in metrics"""
        # Simple anomaly detection using z-score
        for metric_type in MetricType:
            summary = await self.get_metric_summary(
                instance_id,
                metric_type,
                timedelta(hours=24)
            )
            
            if not summary or summary.sample_count < 10:
                continue
            
            # Check if current value is anomalous
            if summary.std_deviation > 0:
                z_score = abs(summary.current_value - summary.average) / summary.std_deviation
                
                if z_score > 3:  # 3 standard deviations
                    await self._create_alert(
                        instance_id,
                        AlertType.ANOMALY_DETECTED,
                        AlertSeverity.WARNING,
                        f"Anomaly detected in {metric_type.value}",
                        {
                            "metric_type": metric_type.value,
                            "current_value": summary.current_value,
                            "average": summary.average,
                            "z_score": z_score
                        }
                    )
    
    async def _check_metric_alerts(self, instance_id: UUID):
        """Check metrics against alert thresholds"""
        # Check error rate
        error_summary = await self.get_metric_summary(
            instance_id,
            MetricType.ERROR_RATE,
            timedelta(minutes=15)
        )
        
        if error_summary and error_summary.current_value > self.alert_thresholds[AlertType.HIGH_ERROR_RATE]:
            await self._create_alert(
                instance_id,
                AlertType.HIGH_ERROR_RATE,
                AlertSeverity.ERROR,
                f"High error rate: {error_summary.current_value*100:.1f}%",
                {"error_rate": error_summary.current_value}
            )
        
        # Check spend threshold
        spend_status = await self.spend_service.get_spend_status(instance_id)
        if spend_status['daily_percentage'] > self.alert_thresholds[AlertType.SPEND_THRESHOLD] * 100:
            await self._create_alert(
                instance_id,
                AlertType.SPEND_THRESHOLD,
                AlertSeverity.WARNING,
                f"Approaching daily spend limit: {spend_status['daily_percentage']:.1f}%",
                spend_status
            )
        
        # Check performance degradation
        perf_summary = await self.get_metric_summary(
            instance_id,
            MetricType.RESPONSE_TIME,
            timedelta(hours=1)
        )
        
        if perf_summary and perf_summary.sample_count > 5:
            baseline = perf_summary.percentile_50
            if perf_summary.current_value > baseline * self.alert_thresholds[AlertType.PERFORMANCE_DEGRADATION]:
                await self._create_alert(
                    instance_id,
                    AlertType.PERFORMANCE_DEGRADATION,
                    AlertSeverity.WARNING,
                    "Performance degradation detected",
                    {
                        "current_response_time": perf_summary.current_value,
                        "baseline": baseline,
                        "degradation_factor": perf_summary.current_value / baseline
                    }
                )
        
        # Check prolonged busy state
        state = await self.lifecycle_service.get_instance_state(instance_id)
        if state == InstanceState.BUSY:
            duration = await self._get_state_duration(instance_id, state)
            if duration > self.alert_thresholds[AlertType.PROLONGED_BUSY_STATE]:
                await self._create_alert(
                    instance_id,
                    AlertType.PROLONGED_BUSY_STATE,
                    AlertSeverity.WARNING,
                    f"Instance busy for {duration.total_seconds()/3600:.1f} hours",
                    {"duration_hours": duration.total_seconds()/3600}
                )
    
    async def set_sla_targets(self, instance_id: UUID, targets: List[SLATarget]):
        """Set SLA targets for an instance"""
        self._sla_targets[instance_id] = targets
        logger.info(f"Set {len(targets)} SLA targets for instance {instance_id}")
    
    async def _check_sla_compliance(self, instance_id: UUID):
        """Check SLA compliance"""
        if instance_id not in self._sla_targets:
            return
        
        for target in self._sla_targets[instance_id]:
            summary = await self.get_metric_summary(
                instance_id,
                target.metric_type,
                target.measurement_window
            )
            
            if not summary:
                continue
            
            # Check if target is violated
            violated = False
            if target.comparison == "less_than":
                violated = summary.average >= target.target_value
            elif target.comparison == "greater_than":
                violated = summary.average <= target.target_value
            
            if violated:
                await self._create_alert(
                    instance_id,
                    AlertType.SLA_VIOLATION,
                    AlertSeverity.ERROR,
                    f"SLA violation: {target.metric_type.value} {target.comparison} {target.target_value}",
                    {
                        "metric_type": target.metric_type.value,
                        "target_value": target.target_value,
                        "actual_value": summary.average,
                        "comparison": target.comparison
                    }
                )
    
    async def _create_alert(
        self,
        instance_id: UUID,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        details: Dict[str, Any]
    ):
        """Create a new alert"""
        # Check if similar alert already exists
        existing_alerts = self._alerts[instance_id]
        for alert in existing_alerts:
            if (alert.alert_type == alert_type and 
                not alert.resolved and
                alert.created_at > datetime.utcnow() - timedelta(minutes=15)):
                # Don't create duplicate alerts
                return
        
        alert = Alert(
            id=UUID(bytes=instance_id.bytes + alert_type.value.encode()[:16].ljust(16, b'\0')),
            instance_id=instance_id,
            alert_type=alert_type,
            severity=severity,
            message=message,
            details=details,
            created_at=datetime.utcnow()
        )
        
        self._alerts[instance_id].append(alert)
        
        # Log alert
        logger.warning(f"Alert created for {instance_id}: {message}")
        
        # Persist alert
        await self._persist_alert(alert)
    
    async def get_active_alerts(self, instance_id: Optional[UUID] = None) -> List[Alert]:
        """Get active alerts"""
        if instance_id:
            return [a for a in self._alerts.get(instance_id, []) if not a.resolved]
        else:
            all_alerts = []
            for alerts in self._alerts.values():
                all_alerts.extend([a for a in alerts if not a.resolved])
            return all_alerts
    
    async def resolve_alert(self, alert_id: UUID):
        """Resolve an alert"""
        for alerts in self._alerts.values():
            for alert in alerts:
                if alert.id == alert_id:
                    alert.resolved = True
                    alert.resolved_at = datetime.utcnow()
                    await self._update_alert_status(alert)
                    return
    
    async def get_monitoring_dashboard(self, instance_id: UUID) -> Dict[str, Any]:
        """Get comprehensive monitoring dashboard data"""
        # Get current state
        state = await self.lifecycle_service.get_instance_state(instance_id)
        health = await self.lifecycle_service.check_instance_health(instance_id)
        
        # Get metric summaries
        metric_summaries = {}
        for metric_type in MetricType:
            summary = await self.get_metric_summary(instance_id, metric_type)
            if summary:
                metric_summaries[metric_type.value] = {
                    "current": summary.current_value,
                    "average": summary.average,
                    "min": summary.min_value,
                    "max": summary.max_value,
                    "trend": summary.trend,
                    "samples": summary.sample_count
                }
        
        # Get active alerts
        alerts = await self.get_active_alerts(instance_id)
        
        # Get spend info
        spend_status = await self.spend_service.get_spend_status(instance_id)
        
        # Build dashboard
        dashboard = {
            "instance_id": str(instance_id),
            "current_state": state.value if state else "unknown",
            "health_status": health.status.value,
            "health_score": self._calculate_health_score(health),
            "metrics": metric_summaries,
            "active_alerts": len(alerts),
            "alerts": [
                {
                    "type": a.alert_type.value,
                    "severity": a.severity.value,
                    "message": a.message,
                    "created_at": a.created_at.isoformat()
                }
                for a in alerts
            ],
            "spend": {
                "daily_used": spend_status['daily_percentage'],
                "monthly_used": spend_status['monthly_percentage'],
                "daily_remaining": spend_status['daily_remaining'],
                "monthly_remaining": spend_status['monthly_remaining']
            },
            "sla_compliance": await self._get_sla_compliance_summary(instance_id)
        }
        
        return dashboard
    
    async def _get_sla_compliance_summary(self, instance_id: UUID) -> Dict[str, Any]:
        """Get SLA compliance summary"""
        if instance_id not in self._sla_targets:
            return {"has_sla": False, "targets": []}
        
        targets_status = []
        for target in self._sla_targets[instance_id]:
            summary = await self.get_metric_summary(
                instance_id,
                target.metric_type,
                target.measurement_window
            )
            
            if summary:
                met = True
                if target.comparison == "less_than":
                    met = summary.average < target.target_value
                elif target.comparison == "greater_than":
                    met = summary.average > target.target_value
                
                targets_status.append({
                    "metric": target.metric_type.value,
                    "target": target.target_value,
                    "actual": summary.average,
                    "met": met
                })
        
        compliance_rate = sum(1 for t in targets_status if t["met"]) / len(targets_status) if targets_status else 0
        
        return {
            "has_sla": True,
            "compliance_rate": compliance_rate * 100,
            "targets": targets_status
        }
    
    async def _persist_metrics(self):
        """Persist all metrics to database"""
        for instance_id, metrics in self._metrics.items():
            await self._persist_instance_metrics(instance_id)
    
    async def _persist_instance_metrics(self, instance_id: UUID):
        """Persist metrics for a specific instance"""
        # This would typically write to a time-series database
        # For now, we'll store in PostgreSQL
        
        for metric_type, points in self._metrics[instance_id].items():
            if not points:
                continue
            
            # Batch insert metric points
            values = []
            for point in points:
                values.append((
                    instance_id,
                    metric_type.value,
                    point.timestamp,
                    point.value,
                    json.dumps(point.metadata) if point.metadata else None
                ))
            
            if values:
                # Note: This table would need to be created in migrations
                query = """
                INSERT INTO orchestrator.instance_metrics 
                (instance_id, metric_type, timestamp, value, metadata)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (instance_id, metric_type, timestamp) DO NOTHING
                """
                
                for value in values:
                    try:
                        await self.db.execute_query(query, *value)
                    except Exception as e:
                        logger.error(f"Failed to persist metric: {e}")
    
    async def _persist_alert(self, alert: Alert):
        """Persist alert to database"""
        # Note: This table would need to be created in migrations
        query = """
        INSERT INTO orchestrator.monitoring_alerts
        (id, instance_id, alert_type, severity, message, details, created_at, resolved)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (id) DO NOTHING
        """
        
        try:
            await self.db.execute_query(
                query,
                alert.id,
                alert.instance_id,
                alert.alert_type.value,
                alert.severity.value,
                alert.message,
                json.dumps(alert.details),
                alert.created_at,
                alert.resolved
            )
        except Exception as e:
            logger.error(f"Failed to persist alert: {e}")
    
    async def _update_alert_status(self, alert: Alert):
        """Update alert resolution status"""
        query = """
        UPDATE orchestrator.monitoring_alerts
        SET resolved = $2, resolved_at = $3
        WHERE id = $1
        """
        
        try:
            await self.db.execute_query(
                query,
                alert.id,
                alert.resolved,
                alert.resolved_at
            )
        except Exception as e:
            logger.error(f"Failed to update alert status: {e}")
    
    async def _load_historical_metrics(self):
        """Load recent historical metrics from database"""
        # Load metrics from last hour for active instances
        query = """
        SELECT instance_id, metric_type, timestamp, value, metadata
        FROM orchestrator.instance_metrics
        WHERE timestamp >= NOW() - INTERVAL '1 hour'
        ORDER BY timestamp
        """
        
        try:
            results = await self.db.execute_query(query)
            
            for row in results:
                instance_id = row['instance_id']
                metric_type = MetricType(row['metric_type'])
                
                point = MetricPoint(
                    timestamp=row['timestamp'],
                    value=row['value'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else None
                )
                
                self._metrics[instance_id][metric_type].append(point)
                
        except Exception as e:
            logger.warning(f"Could not load historical metrics: {e}")
    
    async def _periodic_persistence(self):
        """Periodically persist metrics to database"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self._persist_metrics()
                
                # Clean up old metrics from memory
                cutoff = datetime.utcnow() - timedelta(hours=2)
                for instance_metrics in self._metrics.values():
                    for points in instance_metrics.values():
                        while points and points[0].timestamp < cutoff:
                            points.popleft()
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic persistence: {e}")