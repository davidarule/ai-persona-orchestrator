"""
Persona Instance Lifecycle Management Service

Manages the complete lifecycle of persona instances from creation through termination,
including state transitions, health monitoring, and automated maintenance.
"""

import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from uuid import UUID
from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
import json
import logging

from backend.services.database import DatabaseManager
from backend.models.persona_instance import PersonaInstance, PersonaInstanceResponse
from backend.services.persona_instance_service import PersonaInstanceService
from backend.services.spend_tracking_service import SpendTrackingService
from backend.services.llm_provider_service import LLMProviderService


# Configure logging
logger = logging.getLogger(__name__)


class InstanceState(str, Enum):
    """Persona instance lifecycle states"""
    PROVISIONING = "provisioning"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    BUSY = "busy"
    PAUSED = "paused"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    TERMINATING = "terminating"
    TERMINATED = "terminated"


class InstanceHealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class LifecycleEvent:
    """Represents a lifecycle event"""
    instance_id: UUID
    event_type: str
    from_state: InstanceState
    to_state: InstanceState
    timestamp: datetime
    details: Dict[str, Any]
    triggered_by: str  # system, user, automation
    success: bool
    error_message: Optional[str] = None


@dataclass
class HealthCheck:
    """Health check result"""
    instance_id: UUID
    status: InstanceHealthStatus
    checks: Dict[str, bool]
    metrics: Dict[str, Any]
    issues: List[str]
    recommendations: List[str]
    timestamp: datetime


@dataclass
class MaintenanceWindow:
    """Scheduled maintenance window"""
    instance_id: UUID
    start_time: datetime
    end_time: datetime
    maintenance_type: str
    auto_resume: bool
    notification_sent: bool


class PersonaInstanceLifecycle:
    """
    Manages the complete lifecycle of persona instances
    
    Lifecycle stages:
    1. PROVISIONING: Instance created but not yet initialized
    2. INITIALIZING: Setting up connections, validating access
    3. ACTIVE: Ready for work, accepting tasks
    4. BUSY: Currently processing tasks
    5. PAUSED: Temporarily suspended (manual or automatic)
    6. ERROR: Encountered critical error, needs intervention
    7. MAINTENANCE: Undergoing maintenance operations
    8. TERMINATING: Cleanup in progress
    9. TERMINATED: Instance removed, resources released
    """
    
    # Valid state transitions
    VALID_TRANSITIONS = {
        InstanceState.PROVISIONING: [InstanceState.INITIALIZING, InstanceState.ERROR, InstanceState.TERMINATING],
        InstanceState.INITIALIZING: [InstanceState.ACTIVE, InstanceState.ERROR, InstanceState.TERMINATING],
        InstanceState.ACTIVE: [InstanceState.BUSY, InstanceState.PAUSED, InstanceState.ERROR, InstanceState.MAINTENANCE, InstanceState.TERMINATING],
        InstanceState.BUSY: [InstanceState.ACTIVE, InstanceState.ERROR, InstanceState.PAUSED, InstanceState.TERMINATING],
        InstanceState.PAUSED: [InstanceState.ACTIVE, InstanceState.MAINTENANCE, InstanceState.TERMINATING],
        InstanceState.ERROR: [InstanceState.INITIALIZING, InstanceState.MAINTENANCE, InstanceState.TERMINATING],
        InstanceState.MAINTENANCE: [InstanceState.ACTIVE, InstanceState.ERROR, InstanceState.TERMINATING],
        InstanceState.TERMINATING: [InstanceState.TERMINATED],
        InstanceState.TERMINATED: []  # Final state
    }
    
    # Automatic state transition rules
    AUTO_TRANSITIONS = {
        "spend_limit_exceeded": (InstanceState.ACTIVE, InstanceState.PAUSED),
        "health_check_failed": (InstanceState.ACTIVE, InstanceState.ERROR),
        "maintenance_start": (InstanceState.ACTIVE, InstanceState.MAINTENANCE),
        "maintenance_complete": (InstanceState.MAINTENANCE, InstanceState.ACTIVE),
        "initialization_complete": (InstanceState.INITIALIZING, InstanceState.ACTIVE),
        "error_resolved": (InstanceState.ERROR, InstanceState.INITIALIZING)
    }
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.instance_service = PersonaInstanceService(db_manager)
        self.spend_service = SpendTrackingService(db_manager)
        self.llm_service = LLMProviderService(db_manager)
        self._lifecycle_cache: Dict[UUID, InstanceState] = {}
        self._health_cache: Dict[UUID, HealthCheck] = {}
        self._maintenance_windows: Dict[UUID, MaintenanceWindow] = {}
    
    async def initialize(self):
        """Initialize lifecycle service"""
        await self.spend_service.initialize()
        await self.llm_service.initialize()
        
        # Create lifecycle state table if not exists
        await self._ensure_lifecycle_tables()
        
        # Load existing states into cache
        await self._load_lifecycle_states()
    
    async def close(self):
        """Clean up resources"""
        await self.spend_service.close()
        await self.llm_service.close()
    
    async def provision_instance(self, instance_id: UUID) -> LifecycleEvent:
        """
        Begin provisioning a new instance
        
        This is called after instance creation to start lifecycle management
        """
        # Set initial state
        await self._set_instance_state(instance_id, InstanceState.PROVISIONING)
        
        # Record lifecycle event
        event = await self._record_lifecycle_event(
            instance_id=instance_id,
            event_type="instance_provisioned",
            from_state=None,
            to_state=InstanceState.PROVISIONING,
            details={"action": "lifecycle_started"},
            triggered_by="system"
        )
        
        # Start initialization process asynchronously
        asyncio.create_task(self._initialize_instance(instance_id))
        
        return event
    
    async def _initialize_instance(self, instance_id: UUID):
        """Initialize instance (async background task)"""
        try:
            # Transition to initializing
            await self.transition_state(
                instance_id,
                InstanceState.INITIALIZING,
                triggered_by="system",
                details={"phase": "initialization_start"}
            )
            
            # Get instance details
            instance = await self.instance_service.get_instance(instance_id)
            if not instance:
                raise ValueError(f"Instance {instance_id} not found")
            
            # Validate LLM providers
            validation_passed = True
            for provider in instance.llm_providers:
                is_valid = await self.llm_service.validate_provider(provider)
                if not is_valid:
                    validation_passed = False
                    logger.warning(f"LLM provider validation failed for {provider.provider}")
            
            if not validation_passed:
                await self.transition_state(
                    instance_id,
                    InstanceState.ERROR,
                    triggered_by="system",
                    details={"error": "LLM provider validation failed"}
                )
                return
            
            # Perform health check
            health = await self.check_instance_health(instance_id)
            if health.status == InstanceHealthStatus.CRITICAL:
                await self.transition_state(
                    instance_id,
                    InstanceState.ERROR,
                    triggered_by="system",
                    details={"error": "Initial health check failed", "issues": health.issues}
                )
                return
            
            # Successfully initialized
            await self.transition_state(
                instance_id,
                InstanceState.ACTIVE,
                triggered_by="system",
                details={"phase": "initialization_complete"}
            )
            
        except Exception as e:
            logger.error(f"Instance initialization failed: {e}")
            await self.transition_state(
                instance_id,
                InstanceState.ERROR,
                triggered_by="system",
                details={"error": str(e)}
            )
    
    async def get_instance_state(self, instance_id: UUID) -> Optional[InstanceState]:
        """Get current lifecycle state of an instance"""
        # Check cache first
        if instance_id in self._lifecycle_cache:
            return self._lifecycle_cache[instance_id]
        
        # Query database
        query = """
        SELECT current_state 
        FROM orchestrator.instance_lifecycle
        WHERE instance_id = $1
        """
        
        result = await self.db.execute_query(query, instance_id, fetch_one=True)
        if result:
            state = InstanceState(result['current_state'])
            self._lifecycle_cache[instance_id] = state
            return state
        
        return None
    
    async def transition_state(
        self,
        instance_id: UUID,
        to_state: InstanceState,
        triggered_by: str = "system",
        details: Optional[Dict[str, Any]] = None
    ) -> LifecycleEvent:
        """
        Transition instance to a new state
        
        Args:
            instance_id: Instance to transition
            to_state: Target state
            triggered_by: Who triggered the transition (system, user, automation)
            details: Additional context about the transition
            
        Returns:
            LifecycleEvent recording the transition
            
        Raises:
            ValueError: If transition is invalid
        """
        current_state = await self.get_instance_state(instance_id)
        if not current_state:
            # First time - need to provision
            if to_state == InstanceState.PROVISIONING:
                current_state = None
            else:
                raise ValueError(f"Instance {instance_id} has no lifecycle state")
        
        # Validate transition
        if current_state and to_state not in self.VALID_TRANSITIONS.get(current_state, []):
            raise ValueError(
                f"Invalid state transition from {current_state} to {to_state}"
            )
        
        # Perform transition
        await self._set_instance_state(instance_id, to_state)
        
        # Update instance active status based on state
        if to_state in [InstanceState.TERMINATED, InstanceState.ERROR, InstanceState.PAUSED]:
            await self._update_instance_active_status(instance_id, False)
        elif to_state == InstanceState.ACTIVE:
            await self._update_instance_active_status(instance_id, True)
        
        # Record event
        event = await self._record_lifecycle_event(
            instance_id=instance_id,
            event_type=f"state_transition",
            from_state=current_state,
            to_state=to_state,
            details=details or {},
            triggered_by=triggered_by
        )
        
        # Trigger state-specific actions
        await self._handle_state_entry(instance_id, to_state, triggered_by)
        
        return event
    
    async def check_instance_health(self, instance_id: UUID) -> HealthCheck:
        """
        Perform comprehensive health check on instance
        
        Checks:
        - Instance exists and basic info available
        - LLM provider connectivity
        - Spend limits not exceeded
        - Recent activity patterns
        - Error rates
        """
        checks = {}
        issues = []
        recommendations = []
        metrics = {}
        
        # Check instance exists
        instance = await self.instance_service.get_instance(instance_id)
        checks['instance_exists'] = instance is not None
        
        if not instance:
            return HealthCheck(
                instance_id=instance_id,
                status=InstanceHealthStatus.CRITICAL,
                checks=checks,
                metrics=metrics,
                issues=["Instance not found"],
                recommendations=["Verify instance ID"],
                timestamp=datetime.utcnow()
            )
        
        # Check lifecycle state
        state = await self.get_instance_state(instance_id)
        checks['has_lifecycle_state'] = state is not None
        metrics['current_state'] = state.value if state else "unknown"
        
        # Check spend limits
        spend_status = await self.spend_service.get_spend_status(instance_id)
        checks['spend_within_limits'] = not (spend_status['daily_exceeded'] or spend_status['monthly_exceeded'])
        metrics['daily_spend_percentage'] = spend_status['daily_percentage']
        metrics['monthly_spend_percentage'] = spend_status['monthly_percentage']
        
        if spend_status['daily_exceeded']:
            issues.append("Daily spend limit exceeded")
            recommendations.append("Increase daily spend limit or pause instance")
        
        if spend_status['monthly_percentage'] > 90:
            issues.append("Monthly spend approaching limit")
            recommendations.append("Monitor spend closely or increase monthly limit")
        
        # Check LLM provider health
        provider_health = True
        for provider in instance.llm_providers:
            is_valid = await self.llm_service.validate_provider(provider)
            if not is_valid:
                provider_health = False
                issues.append(f"LLM provider {provider.provider} validation failed")
                recommendations.append(f"Check API key for {provider.provider}")
        
        checks['llm_providers_healthy'] = provider_health
        
        # Check recent activity
        recent_activity = await self._check_recent_activity(instance_id)
        checks['has_recent_activity'] = recent_activity['active']
        metrics['hours_since_last_activity'] = recent_activity['hours_since_last']
        
        if not recent_activity['active'] and state == InstanceState.ACTIVE:
            issues.append("No recent activity detected")
            recommendations.append("Consider pausing inactive instance to save costs")
        
        # Check error rate
        error_rate = await self._check_error_rate(instance_id)
        checks['acceptable_error_rate'] = error_rate['acceptable']
        metrics['error_rate_percentage'] = error_rate['percentage']
        
        if not error_rate['acceptable']:
            issues.append(f"High error rate: {error_rate['percentage']:.1f}%")
            recommendations.append("Review recent errors and adjust configuration")
        
        # Determine overall status
        critical_checks = ['instance_exists', 'has_lifecycle_state', 'llm_providers_healthy']
        warning_checks = ['spend_within_limits', 'acceptable_error_rate']
        
        if any(not checks.get(check, False) for check in critical_checks):
            status = InstanceHealthStatus.CRITICAL
        elif any(not checks.get(check, False) for check in warning_checks):
            status = InstanceHealthStatus.WARNING
        elif len(issues) > 0:
            status = InstanceHealthStatus.WARNING
        else:
            status = InstanceHealthStatus.HEALTHY
        
        health_check = HealthCheck(
            instance_id=instance_id,
            status=status,
            checks=checks,
            metrics=metrics,
            issues=issues,
            recommendations=recommendations,
            timestamp=datetime.utcnow()
        )
        
        # Cache result
        self._health_cache[instance_id] = health_check
        
        return health_check
    
    async def pause_instance(
        self,
        instance_id: UUID,
        reason: str,
        auto_resume_after: Optional[timedelta] = None,
        triggered_by: str = "user"
    ) -> LifecycleEvent:
        """Pause an instance with optional auto-resume"""
        current_state = await self.get_instance_state(instance_id)
        
        # Only pause if in a pausable state
        if current_state not in [InstanceState.ACTIVE, InstanceState.BUSY]:
            raise ValueError(f"Cannot pause instance in state {current_state}")
        
        # Transition to paused
        event = await self.transition_state(
            instance_id,
            InstanceState.PAUSED,
            triggered_by=triggered_by,
            details={
                "reason": reason,
                "auto_resume": auto_resume_after is not None,
                "resume_after_seconds": auto_resume_after.total_seconds() if auto_resume_after else None
            }
        )
        
        # Schedule auto-resume if requested
        if auto_resume_after:
            resume_time = datetime.utcnow() + auto_resume_after
            asyncio.create_task(self._schedule_auto_resume(instance_id, resume_time))
        
        return event
    
    async def resume_instance(
        self,
        instance_id: UUID,
        triggered_by: str = "user"
    ) -> LifecycleEvent:
        """Resume a paused instance"""
        current_state = await self.get_instance_state(instance_id)
        
        if current_state != InstanceState.PAUSED:
            raise ValueError(f"Cannot resume instance in state {current_state}")
        
        # Perform health check before resuming
        health = await self.check_instance_health(instance_id)
        
        if health.status == InstanceHealthStatus.CRITICAL:
            # Transition to error instead
            return await self.transition_state(
                instance_id,
                InstanceState.ERROR,
                triggered_by="system",
                details={
                    "reason": "Health check failed during resume",
                    "issues": health.issues
                }
            )
        
        # Resume to active state
        return await self.transition_state(
            instance_id,
            InstanceState.ACTIVE,
            triggered_by=triggered_by,
            details={"action": "resumed"}
        )
    
    async def schedule_maintenance(
        self,
        instance_id: UUID,
        start_time: datetime,
        duration: timedelta,
        maintenance_type: str,
        auto_resume: bool = True
    ) -> MaintenanceWindow:
        """Schedule maintenance for an instance"""
        end_time = start_time + duration
        
        window = MaintenanceWindow(
            instance_id=instance_id,
            start_time=start_time,
            end_time=end_time,
            maintenance_type=maintenance_type,
            auto_resume=auto_resume,
            notification_sent=False
        )
        
        self._maintenance_windows[instance_id] = window
        
        # Schedule maintenance start
        asyncio.create_task(self._schedule_maintenance_start(window))
        
        return window
    
    async def terminate_instance(
        self,
        instance_id: UUID,
        reason: str,
        force: bool = False,
        triggered_by: str = "user"
    ) -> LifecycleEvent:
        """
        Begin instance termination process
        
        Args:
            instance_id: Instance to terminate
            reason: Reason for termination
            force: Force termination even if tasks are active
            triggered_by: Who triggered termination
        """
        current_state = await self.get_instance_state(instance_id)
        
        if current_state == InstanceState.TERMINATED:
            raise ValueError("Instance already terminated")
        
        # Check for active tasks unless forced
        if not force:
            instance = await self.instance_service.get_instance(instance_id)
            if instance and instance.current_task_count > 0:
                raise ValueError(
                    f"Cannot terminate instance with {instance.current_task_count} active tasks. "
                    "Use force=True to override."
                )
        
        # Transition to terminating
        event = await self.transition_state(
            instance_id,
            InstanceState.TERMINATING,
            triggered_by=triggered_by,
            details={
                "reason": reason,
                "forced": force
            }
        )
        
        # Perform cleanup asynchronously
        asyncio.create_task(self._cleanup_instance(instance_id))
        
        return event
    
    async def get_lifecycle_history(
        self,
        instance_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[LifecycleEvent]:
        """Get lifecycle event history for an instance"""
        query = """
        SELECT 
            event_type,
            from_state,
            to_state,
            timestamp,
            details,
            triggered_by,
            success,
            error_message
        FROM orchestrator.lifecycle_events
        WHERE instance_id = $1
        """
        
        params = [instance_id]
        
        if start_date:
            query += f" AND timestamp >= ${len(params) + 1}"
            params.append(start_date)
        
        if end_date:
            query += f" AND timestamp <= ${len(params) + 1}"
            params.append(end_date)
        
        query += " ORDER BY timestamp DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)
        
        results = await self.db.execute_query(query, *params)
        
        events = []
        for row in results:
            events.append(LifecycleEvent(
                instance_id=instance_id,
                event_type=row['event_type'],
                from_state=InstanceState(row['from_state']) if row['from_state'] else None,
                to_state=InstanceState(row['to_state']),
                timestamp=row['timestamp'],
                details=json.loads(row['details']) if row['details'] else {},
                triggered_by=row['triggered_by'],
                success=row['success'],
                error_message=row['error_message']
            ))
        
        return events
    
    async def monitor_all_instances(self) -> Dict[str, Any]:
        """Monitor health and state of all active instances"""
        # Get all active instances
        instances = await self.instance_service.list_instances(is_active=True)
        
        monitoring_results = {
            "total_instances": len(instances),
            "healthy_instances": 0,
            "warning_instances": 0,
            "critical_instances": 0,
            "by_state": {},
            "issues_found": [],
            "auto_transitions": []
        }
        
        for instance in instances:
            # Check health
            health = await self.check_instance_health(instance.id)
            
            if health.status == InstanceHealthStatus.HEALTHY:
                monitoring_results["healthy_instances"] += 1
            elif health.status == InstanceHealthStatus.WARNING:
                monitoring_results["warning_instances"] += 1
            else:
                monitoring_results["critical_instances"] += 1
                monitoring_results["issues_found"].extend(health.issues)
            
            # Check state
            state = await self.get_instance_state(instance.id)
            if state:
                monitoring_results["by_state"][state.value] = monitoring_results["by_state"].get(state.value, 0) + 1
            
            # Check for automatic transitions
            auto_transition = await self._check_auto_transitions(instance.id, health)
            if auto_transition:
                monitoring_results["auto_transitions"].append(auto_transition)
        
        return monitoring_results
    
    async def _check_auto_transitions(
        self,
        instance_id: UUID,
        health: HealthCheck
    ) -> Optional[Dict[str, Any]]:
        """Check if automatic state transitions are needed"""
        current_state = await self.get_instance_state(instance_id)
        
        if not current_state:
            return None
        
        # Check spend limits
        if current_state == InstanceState.ACTIVE:
            spend_status = await self.spend_service.get_spend_status(instance_id)
            
            if spend_status['daily_exceeded'] or spend_status['monthly_exceeded']:
                # Auto-pause due to spend limit
                await self.pause_instance(
                    instance_id,
                    reason="Spend limit exceeded",
                    triggered_by="automation"
                )
                return {
                    "instance_id": str(instance_id),
                    "transition": "spend_limit_exceeded",
                    "from_state": current_state.value,
                    "to_state": InstanceState.PAUSED.value
                }
        
        # Check health status
        if health.status == InstanceHealthStatus.CRITICAL and current_state == InstanceState.ACTIVE:
            # Transition to error due to health check
            await self.transition_state(
                instance_id,
                InstanceState.ERROR,
                triggered_by="automation",
                details={"reason": "Critical health check failure", "issues": health.issues}
            )
            return {
                "instance_id": str(instance_id),
                "transition": "health_check_failed",
                "from_state": current_state.value,
                "to_state": InstanceState.ERROR.value
            }
        
        return None
    
    async def _set_instance_state(self, instance_id: UUID, state: InstanceState):
        """Set instance state in database and cache"""
        query = """
        INSERT INTO orchestrator.instance_lifecycle (instance_id, current_state, last_updated)
        VALUES ($1, $2, NOW())
        ON CONFLICT (instance_id) DO UPDATE 
        SET current_state = $2, last_updated = NOW()
        """
        
        await self.db.execute_query(query, instance_id, state.value)
        self._lifecycle_cache[instance_id] = state
    
    async def _record_lifecycle_event(
        self,
        instance_id: UUID,
        event_type: str,
        from_state: Optional[InstanceState],
        to_state: InstanceState,
        details: Dict[str, Any],
        triggered_by: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> LifecycleEvent:
        """Record lifecycle event in database"""
        event = LifecycleEvent(
            instance_id=instance_id,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.utcnow(),
            details=details,
            triggered_by=triggered_by,
            success=success,
            error_message=error_message
        )
        
        query = """
        INSERT INTO orchestrator.lifecycle_events (
            instance_id, event_type, from_state, to_state,
            timestamp, details, triggered_by, success, error_message
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        
        await self.db.execute_query(
            query,
            instance_id,
            event_type,
            from_state.value if from_state else None,
            to_state.value,
            event.timestamp,
            json.dumps(details),
            triggered_by,
            success,
            error_message
        )
        
        return event
    
    async def _update_instance_active_status(self, instance_id: UUID, is_active: bool):
        """Update instance active status"""
        query = """
        UPDATE orchestrator.persona_instances
        SET is_active = $2, updated_at = NOW()
        WHERE id = $1
        """
        
        await self.db.execute_query(query, instance_id, is_active)
    
    async def _handle_state_entry(
        self,
        instance_id: UUID,
        state: InstanceState,
        triggered_by: str
    ):
        """Handle actions when entering a new state"""
        if state == InstanceState.ACTIVE:
            # Clear any error counts
            await self._reset_error_metrics(instance_id)
            
        elif state == InstanceState.ERROR:
            # Send notification about error state
            logger.error(f"Instance {instance_id} entered ERROR state")
            
        elif state == InstanceState.MAINTENANCE:
            # Pause any active tasks
            logger.info(f"Instance {instance_id} entering maintenance")
            
        elif state == InstanceState.TERMINATED:
            # Final cleanup
            await self._finalize_termination(instance_id)
    
    async def _check_recent_activity(self, instance_id: UUID) -> Dict[str, Any]:
        """Check if instance has recent activity"""
        query = """
        SELECT MAX(created_at) as last_activity
        FROM orchestrator.spend_tracking
        WHERE instance_id = $1
        """
        
        result = await self.db.execute_query(query, instance_id, fetch_one=True)
        
        if result and result is not None and result.get('last_activity'):
            hours_since = (datetime.utcnow() - result['last_activity']).total_seconds() / 3600
            return {
                "active": hours_since < 24,  # Active if used in last 24 hours
                "hours_since_last": hours_since,
                "last_activity": result['last_activity']
            }
        
        return {
            "active": False,
            "hours_since_last": float('inf'),
            "last_activity": None
        }
    
    async def _check_error_rate(self, instance_id: UUID) -> Dict[str, Any]:
        """Check error rate for instance"""
        # Check LLM usage errors in last 24 hours
        query = """
        SELECT 
            COUNT(*) FILTER (WHERE success = false) as error_count,
            COUNT(*) as total_count
        FROM orchestrator.llm_usage_logs
        WHERE instance_id = $1
        AND created_at >= NOW() - INTERVAL '24 hours'
        """
        
        result = await self.db.execute_query(query, str(instance_id), fetch_one=True)
        
        if result and result is not None and result.get('total_count', 0) > 0:
            error_percentage = (result['error_count'] / result['total_count']) * 100
            return {
                "acceptable": error_percentage < 10,  # Less than 10% errors
                "percentage": error_percentage,
                "error_count": result['error_count'],
                "total_count": result['total_count']
            }
        
        return {
            "acceptable": True,
            "percentage": 0,
            "error_count": 0,
            "total_count": 0
        }
    
    async def _reset_error_metrics(self, instance_id: UUID):
        """Reset error metrics when instance becomes healthy"""
        # Could implement error count reset logic here
        pass
    
    async def _schedule_auto_resume(self, instance_id: UUID, resume_time: datetime):
        """Schedule automatic resume of paused instance"""
        wait_seconds = (resume_time - datetime.utcnow()).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
            
            # Check if still paused
            current_state = await self.get_instance_state(instance_id)
            if current_state == InstanceState.PAUSED:
                try:
                    await self.resume_instance(instance_id, triggered_by="automation")
                    logger.info(f"Auto-resumed instance {instance_id}")
                except Exception as e:
                    logger.error(f"Failed to auto-resume instance {instance_id}: {e}")
    
    async def _schedule_maintenance_start(self, window: MaintenanceWindow):
        """Schedule maintenance window start"""
        wait_seconds = (window.start_time - datetime.utcnow()).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
            
            # Start maintenance
            current_state = await self.get_instance_state(window.instance_id)
            if current_state in [InstanceState.ACTIVE, InstanceState.PAUSED]:
                try:
                    await self.transition_state(
                        window.instance_id,
                        InstanceState.MAINTENANCE,
                        triggered_by="automation",
                        details={
                            "maintenance_type": window.maintenance_type,
                            "scheduled_end": window.end_time.isoformat()
                        }
                    )
                    
                    # Schedule maintenance end
                    if window.auto_resume:
                        asyncio.create_task(self._schedule_maintenance_end(window))
                        
                except Exception as e:
                    logger.error(f"Failed to start maintenance for {window.instance_id}: {e}")
    
    async def _schedule_maintenance_end(self, window: MaintenanceWindow):
        """Schedule maintenance window end"""
        wait_seconds = (window.end_time - datetime.utcnow()).total_seconds()
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)
            
            # End maintenance
            current_state = await self.get_instance_state(window.instance_id)
            if current_state == InstanceState.MAINTENANCE:
                try:
                    await self.transition_state(
                        window.instance_id,
                        InstanceState.ACTIVE,
                        triggered_by="automation",
                        details={"maintenance_completed": window.maintenance_type}
                    )
                except Exception as e:
                    logger.error(f"Failed to end maintenance for {window.instance_id}: {e}")
    
    async def _cleanup_instance(self, instance_id: UUID):
        """Perform instance cleanup during termination"""
        try:
            # Wait for any active tasks to complete (with timeout)
            await asyncio.sleep(5)  # Give tasks 5 seconds to complete
            
            # Clear caches
            self._lifecycle_cache.pop(instance_id, None)
            self._health_cache.pop(instance_id, None)
            self._maintenance_windows.pop(instance_id, None)
            
            # Transition to terminated
            await self._set_instance_state(instance_id, InstanceState.TERMINATED)
            
            # Record final event
            await self._record_lifecycle_event(
                instance_id=instance_id,
                event_type="instance_terminated",
                from_state=InstanceState.TERMINATING,
                to_state=InstanceState.TERMINATED,
                details={"cleanup": "completed"},
                triggered_by="system"
            )
            
        except Exception as e:
            logger.error(f"Error during instance cleanup: {e}")
    
    async def _finalize_termination(self, instance_id: UUID):
        """Final cleanup after termination"""
        # This is where we would clean up any external resources
        logger.info(f"Instance {instance_id} termination finalized")
    
    async def _ensure_lifecycle_tables(self):
        """Ensure lifecycle tracking tables exist"""
        # These would be created by migrations, but we check here
        tables_check = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'orchestrator' 
            AND table_name = 'instance_lifecycle'
        )
        """
        
        result = await self.db.execute_query(tables_check, fetch_one=True)
        if not result['exists']:
            logger.warning("Lifecycle tables not found - ensure migrations are run")
    
    async def _load_lifecycle_states(self):
        """Load existing lifecycle states into cache"""
        query = """
        SELECT instance_id, current_state
        FROM orchestrator.instance_lifecycle
        WHERE current_state NOT IN ('terminated')
        """
        
        results = await self.db.execute_query(query)
        
        for row in results:
            self._lifecycle_cache[row['instance_id']] = InstanceState(row['current_state'])