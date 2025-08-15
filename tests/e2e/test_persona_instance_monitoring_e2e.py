"""
End-to-End tests for Persona Instance Monitoring
Real-world monitoring scenarios with alerts, SLA tracking, and dashboard visualization
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal
import random

from backend.services.persona_instance_monitoring import (
    PersonaInstanceMonitoring,
    MetricType,
    AlertType,
    AlertSeverity,
    SLATarget
)
from backend.services.persona_instance_lifecycle import PersonaInstanceLifecycle, InstanceState
from backend.services.persona_instance_service import PersonaInstanceService
from backend.services.spend_tracking_service import SpendTrackingService
from backend.models.persona_instance import PersonaInstanceCreate, LLMProvider, LLMModel
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.e2e
@pytest.mark.asyncio
class TestPersonaInstanceMonitoringE2E:
    """E2E tests simulating real-world monitoring scenarios"""
    
    @pytest.fixture
    async def services(self, db):
        """Create all required services"""
        monitoring = PersonaInstanceMonitoring(db)
        lifecycle = PersonaInstanceLifecycle(db)
        instance = PersonaInstanceService(db)
        spend = SpendTrackingService(db)
        
        await monitoring.initialize()
        await lifecycle.initialize()
        await spend.initialize()
        
        yield {
            "monitoring": monitoring,
            "lifecycle": lifecycle,
            "instance": instance,
            "spend": spend
        }
        
        await monitoring.close()
        await lifecycle.close()
        await spend.close()
    
    @pytest.fixture
    async def test_persona_types(self, db):
        """Create test persona types"""
        repo = PersonaTypeRepository(db)
        types = {}
        
        for name, display, category in [
            ("developer", "Developer", PersonaCategory.DEVELOPMENT),
            ("qa", "QA Engineer", PersonaCategory.TESTING),
            ("devops", "DevOps Engineer", PersonaCategory.OPERATIONS)
        ]:
            persona_type = await repo.create(PersonaTypeCreate(
                type_name=f"{name}-e2e-monitor-{uuid4().hex[:8]}",
                display_name=f"E2E {display}",
                category=category,
                description=f"E2E monitoring test {display}",
                base_workflow_id="wf0"
            ))
            types[name] = persona_type
        
        yield types
        
        # Cleanup
        for persona_type in types.values():
            await db.execute_query(
                "DELETE FROM orchestrator.persona_types WHERE id = $1",
                persona_type.id
            )
    
    async def test_production_monitoring_scenario(self, services, test_persona_types, azure_devops_config):
        """Test production monitoring with SLA tracking and incident response"""
        print("\n=== PRODUCTION MONITORING SCENARIO ===")
        
        # Create production team
        team_instances = []
        team_configs = [
            ("dev1", "developer", "Senior Developer", Decimal("100.00")),
            ("dev2", "developer", "Junior Developer", Decimal("50.00")),
            ("qa1", "qa", "QA Lead", Decimal("75.00")),
            ("devops1", "devops", "DevOps Engineer", Decimal("150.00"))
        ]
        
        for instance_id, persona_type, role, daily_limit in team_configs:
            instance = await services["instance"].create_instance(PersonaInstanceCreate(
                instance_name=f"{role}-{uuid4().hex[:8]}",
                persona_type_id=test_persona_types[persona_type].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project="ProductionApp",
                llm_providers=[
                    LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-4", api_key_env_var="OPENAI_API_KEY"),
                    LLMModel(provider=LLMProvider.ANTHROPIC, model_name="claude-2", api_key_env_var="ANTHROPIC_API_KEY")
                ],
                spend_limit_daily=daily_limit,
                spend_limit_monthly=daily_limit * 30
            ))
            
            # Initialize lifecycle
            await services["lifecycle"].provision_instance(instance.id)
            await services["lifecycle"].activate_instance(instance.id)
            
            # Start monitoring
            await services["monitoring"].start_monitoring(instance.id)
            
            team_instances.append((instance, role))
        
        print("✓ Production team created and monitoring started")
        
        # Set production SLAs
        production_slas = [
            SLATarget(
                metric_type=MetricType.RESPONSE_TIME,
                target_value=3.0,  # 3 seconds max
                comparison="less_than",
                measurement_window=timedelta(minutes=15),
                violation_threshold=5
            ),
            SLATarget(
                metric_type=MetricType.ERROR_RATE,
                target_value=0.02,  # 2% max error rate
                comparison="less_than",
                measurement_window=timedelta(minutes=30),
                violation_threshold=3
            ),
            SLATarget(
                metric_type=MetricType.AVAILABILITY,
                target_value=99.0,  # 99% availability
                comparison="greater_than",
                measurement_window=timedelta(hours=1),
                violation_threshold=1
            )
        ]
        
        for instance, _ in team_instances:
            await services["monitoring"].set_sla_targets(instance.id, production_slas)
        
        print("✓ Production SLAs configured")
        
        # Simulate production workload
        print("\nPhase 1: Normal Operations (2 minutes)")
        
        async def simulate_workload(instance_id, role, phase):
            """Simulate workload for an instance"""
            if phase == "normal":
                response_times = [1.5, 2.0, 1.8, 2.2, 1.9]
                error_rate = 0.01
            elif phase == "degraded":
                response_times = [3.5, 4.0, 3.8, 5.0, 4.2]
                error_rate = 0.05
            else:  # incident
                response_times = [8.0, 10.0, 12.0, 15.0, 20.0]
                error_rate = 0.25
            
            for i in range(10):
                # Record response time
                rt = random.choice(response_times) + random.uniform(-0.5, 0.5)
                services["monitoring"]._record_metric(
                    instance_id,
                    MetricType.RESPONSE_TIME,
                    rt
                )
                
                # Record error rate
                services["monitoring"]._record_metric(
                    instance_id,
                    MetricType.ERROR_RATE,
                    error_rate + random.uniform(-0.005, 0.005)
                )
                
                # Record token usage
                tokens = 100 + random.randint(-20, 50)
                services["monitoring"]._record_metric(
                    instance_id,
                    MetricType.TOKEN_USAGE,
                    tokens
                )
                
                # Record cost
                cost = tokens * 0.0001 * (2 if "gpt-4" in str(instance_id) else 1)
                services["monitoring"]._record_metric(
                    instance_id,
                    MetricType.COST_PER_TASK,
                    cost
                )
                
                # Record availability (simulate some downtime in incident phase)
                availability = 100.0 if phase != "incident" else 85.0 + random.uniform(0, 10)
                services["monitoring"]._record_metric(
                    instance_id,
                    MetricType.AVAILABILITY,
                    availability
                )
                
                await asyncio.sleep(0.1)
        
        # Normal operations
        tasks = [
            simulate_workload(instance.id, role, "normal")
            for instance, role in team_instances
        ]
        await asyncio.gather(*tasks)
        
        # Check metrics
        print("\nMetrics Summary - Normal Operations:")
        for instance, role in team_instances:
            dashboard = await services["monitoring"].get_monitoring_dashboard(instance.id)
            
            metrics = dashboard["metrics"]
            print(f"\n{role}:")
            if MetricType.RESPONSE_TIME.value in metrics:
                print(f"  Response Time: {metrics[MetricType.RESPONSE_TIME.value]['average']:.2f}s")
            if MetricType.ERROR_RATE.value in metrics:
                print(f"  Error Rate: {metrics[MetricType.ERROR_RATE.value]['average']*100:.1f}%")
            print(f"  Health Score: {dashboard['health_score']:.1f}")
            print(f"  Active Alerts: {dashboard['active_alerts']}")
        
        # Simulate performance degradation
        print("\nPhase 2: Performance Degradation (1 minute)")
        
        tasks = [
            simulate_workload(instance.id, role, "degraded")
            for instance, role in team_instances
        ]
        await asyncio.gather(*tasks)
        
        # Check for alerts
        print("\nAlert Status - Performance Degradation:")
        total_alerts = 0
        for instance, role in team_instances:
            alerts = await services["monitoring"].get_active_alerts(instance.id)
            if alerts:
                print(f"\n{role} Alerts:")
                for alert in alerts:
                    print(f"  - {alert.severity.value.upper()}: {alert.message}")
                total_alerts += len(alerts)
        
        print(f"\nTotal Active Alerts: {total_alerts}")
        
        # Simulate incident
        print("\nPhase 3: Production Incident (30 seconds)")
        
        # Only affect some instances to simulate partial outage
        affected_instances = team_instances[:2]
        
        tasks = [
            simulate_workload(instance.id, role, "incident")
            for instance, role in affected_instances
        ]
        await asyncio.gather(*tasks)
        
        # Check SLA violations
        print("\nSLA Compliance Report:")
        for instance, role in team_instances:
            dashboard = await services["monitoring"].get_monitoring_dashboard(instance.id)
            sla_info = dashboard["sla_compliance"]
            
            if sla_info["has_sla"]:
                print(f"\n{role}:")
                print(f"  Compliance Rate: {sla_info['compliance_rate']:.1f}%")
                for target in sla_info["targets"]:
                    status = "✓" if target["met"] else "✗"
                    print(f"  {status} {target['metric']}: {target['actual']:.2f} (target: {target['target']})")
        
        # Generate incident report
        print("\n=== INCIDENT REPORT ===")
        
        critical_alerts = []
        for instance, role in team_instances:
            alerts = await services["monitoring"].get_active_alerts(instance.id)
            critical = [a for a in alerts if a.severity == AlertSeverity.CRITICAL]
            if critical:
                critical_alerts.extend([(role, a) for a in critical])
        
        if critical_alerts:
            print(f"Critical Alerts: {len(critical_alerts)}")
            for role, alert in critical_alerts[:3]:  # Show first 3
                print(f"  - {role}: {alert.message}")
        
        # Cleanup
        for instance, _ in team_instances:
            await services["monitoring"].stop_monitoring(instance.id)
            await services["lifecycle"].terminate_instance(instance.id, "Test complete", force=True)
            await asyncio.sleep(0.1)
            await services["instance"].delete_instance(instance.id)
    
    async def test_anomaly_detection_scenario(self, services, test_persona_types, azure_devops_config):
        """Test anomaly detection in production workloads"""
        print("\n=== ANOMALY DETECTION SCENARIO ===")
        
        # Create test instance
        instance = await services["instance"].create_instance(PersonaInstanceCreate(
            instance_name=f"Anomaly-Detector-{uuid4().hex[:8]}",
            persona_type_id=test_persona_types["developer"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="AnomalyDetection",
            llm_providers=[
                LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-3.5-turbo", api_key_env_var="OPENAI_API_KEY")
            ],
            spend_limit_daily=Decimal("50.00"),
            spend_limit_monthly=Decimal("1000.00")
        ))
        
        await services["lifecycle"].provision_instance(instance.id)
        await services["lifecycle"].activate_instance(instance.id)
        await services["monitoring"].start_monitoring(instance.id)
        
        print("✓ Instance created for anomaly detection")
        
        # Establish baseline pattern
        print("\nPhase 1: Establishing Baseline (2 minutes)")
        
        for hour in range(24):  # Simulate 24 hours of data
            # Normal daily pattern: lower usage at night, peak during day
            base_load = 50 if 9 <= hour <= 17 else 20
            
            for _ in range(5):  # 5 samples per hour
                # Response time varies with load
                response_time = 1.0 + (base_load / 100) + random.uniform(-0.2, 0.2)
                services["monitoring"]._record_metric(
                    instance.id,
                    MetricType.RESPONSE_TIME,
                    response_time
                )
                
                # Token usage follows load
                tokens = base_load * 2 + random.randint(-10, 10)
                services["monitoring"]._record_metric(
                    instance.id,
                    MetricType.TOKEN_USAGE,
                    tokens
                )
                
                # Error rate is normally low
                error_rate = 0.01 + random.uniform(-0.005, 0.005)
                services["monitoring"]._record_metric(
                    instance.id,
                    MetricType.ERROR_RATE,
                    error_rate
                )
        
        print("✓ Baseline established with 120 data points")
        
        # Inject anomalies
        print("\nPhase 2: Injecting Anomalies")
        
        anomalies = [
            ("Sudden spike in response time", MetricType.RESPONSE_TIME, 8.5),
            ("Abnormal token usage", MetricType.TOKEN_USAGE, 500),
            ("Error rate surge", MetricType.ERROR_RATE, 0.15)
        ]
        
        for description, metric_type, anomaly_value in anomalies:
            print(f"  - Injecting: {description}")
            
            # Record anomaly
            services["monitoring"]._record_metric(
                instance.id,
                metric_type,
                anomaly_value
            )
            
            # Run anomaly detection
            await services["monitoring"]._detect_anomalies(instance.id)
        
        # Check detected anomalies
        print("\nPhase 3: Anomaly Detection Results")
        
        alerts = await services["monitoring"].get_active_alerts(instance.id)
        anomaly_alerts = [a for a in alerts if a.alert_type == AlertType.ANOMALY_DETECTED]
        
        print(f"\nDetected {len(anomaly_alerts)} anomalies:")
        for alert in anomaly_alerts:
            details = alert.details
            print(f"  - {details['metric_type']}: Current={details['current_value']:.2f}, "
                  f"Average={details['average']:.2f}, Z-score={details['z_score']:.2f}")
        
        # Get metric summaries with trends
        print("\nMetric Trends:")
        for metric_type in [MetricType.RESPONSE_TIME, MetricType.TOKEN_USAGE, MetricType.ERROR_RATE]:
            summary = await services["monitoring"].get_metric_summary(
                instance.id,
                metric_type,
                timedelta(hours=1)
            )
            
            if summary:
                print(f"  {metric_type.value}:")
                print(f"    Trend: {summary.trend}")
                print(f"    Std Dev: {summary.std_deviation:.3f}")
                print(f"    95th percentile: {summary.percentile_95:.2f}")
        
        # Cleanup
        await services["monitoring"].stop_monitoring(instance.id)
        await services["instance"].delete_instance(instance.id)
    
    async def test_multi_tenant_monitoring_dashboard(self, services, test_persona_types, azure_devops_config, db):
        """Test monitoring dashboard for multi-tenant scenario"""
        print("\n=== MULTI-TENANT MONITORING DASHBOARD ===")
        
        # Create instances for different tenants/projects
        tenants = [
            ("ProjectAlpha", "alpha", 3),
            ("ProjectBeta", "beta", 2),
            ("ProjectGamma", "gamma", 4)
        ]
        
        all_instances = []
        
        for project, prefix, count in tenants:
            print(f"\nCreating {count} instances for {project}")
            
            for i in range(count):
                role = ["developer", "qa", "devops"][i % 3]
                
                instance = await services["instance"].create_instance(PersonaInstanceCreate(
                    instance_name=f"{prefix}-{role}-{i+1}-{uuid4().hex[:8]}",
                    persona_type_id=test_persona_types[role].id,
                    azure_devops_org=azure_devops_config["org_url"],
                    azure_devops_project=project,
                    llm_providers=[
                        LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-3.5-turbo", api_key_env_var="OPENAI_API_KEY")
                    ],
                    spend_limit_daily=Decimal("50.00"),
                    spend_limit_monthly=Decimal("1000.00")
                ))
                
                # Initialize and start monitoring
                await services["lifecycle"].provision_instance(instance.id)
                await services["lifecycle"].activate_instance(instance.id)
                await services["monitoring"].start_monitoring(instance.id)
                
                all_instances.append((instance, project, role))
        
        print(f"\n✓ Created {len(all_instances)} instances across {len(tenants)} projects")
        
        # Simulate varied workloads
        print("\nSimulating varied workloads...")
        
        async def simulate_instance_workload(instance_id, project, role):
            """Simulate workload based on project and role"""
            # Different projects have different load patterns
            load_multipliers = {
                "ProjectAlpha": 1.0,   # Normal load
                "ProjectBeta": 1.5,    # Higher load
                "ProjectGamma": 0.7    # Lower load
            }
            
            # Different roles have different patterns
            role_patterns = {
                "developer": {"response_time": 2.0, "error_rate": 0.02, "tokens": 150},
                "qa": {"response_time": 1.5, "error_rate": 0.01, "tokens": 100},
                "devops": {"response_time": 1.0, "error_rate": 0.005, "tokens": 80}
            }
            
            multiplier = load_multipliers[project]
            pattern = role_patterns[role]
            
            for _ in range(20):
                # Response time
                rt = pattern["response_time"] * multiplier + random.uniform(-0.3, 0.3)
                services["monitoring"]._record_metric(instance_id, MetricType.RESPONSE_TIME, rt)
                
                # Error rate
                er = pattern["error_rate"] * multiplier + random.uniform(-0.005, 0.005)
                services["monitoring"]._record_metric(instance_id, MetricType.ERROR_RATE, max(0, er))
                
                # Token usage
                tokens = pattern["tokens"] * multiplier + random.randint(-20, 20)
                services["monitoring"]._record_metric(instance_id, MetricType.TOKEN_USAGE, tokens)
                
                # Cost
                cost = tokens * 0.00001
                services["monitoring"]._record_metric(instance_id, MetricType.COST_PER_TASK, cost)
                
                # Health score (varies by project health)
                health_base = {"ProjectAlpha": 95, "ProjectBeta": 85, "ProjectGamma": 98}
                health = health_base[project] + random.uniform(-5, 5)
                services["monitoring"]._record_metric(instance_id, MetricType.HEALTH_SCORE, health)
        
        # Run workloads concurrently
        tasks = [
            simulate_instance_workload(instance.id, project, role)
            for instance, project, role in all_instances
        ]
        await asyncio.gather(*tasks)
        
        # Generate project-level dashboards
        print("\n=== PROJECT DASHBOARDS ===")
        
        for project_name, _, _ in tenants:
            print(f"\n{project_name} Dashboard:")
            
            project_instances = [(i, r) for i, p, r in all_instances if p == project_name]
            
            # Aggregate metrics
            total_cost = 0
            avg_response_time = 0
            avg_error_rate = 0
            min_health = 100
            total_alerts = 0
            
            for instance, role in project_instances:
                dashboard = await services["monitoring"].get_monitoring_dashboard(instance.id)
                
                metrics = dashboard["metrics"]
                if MetricType.COST_PER_TASK.value in metrics:
                    total_cost += metrics[MetricType.COST_PER_TASK.value]["average"] * metrics[MetricType.COST_PER_TASK.value]["samples"]
                
                if MetricType.RESPONSE_TIME.value in metrics:
                    avg_response_time += metrics[MetricType.RESPONSE_TIME.value]["average"]
                
                if MetricType.ERROR_RATE.value in metrics:
                    avg_error_rate += metrics[MetricType.ERROR_RATE.value]["average"]
                
                min_health = min(min_health, dashboard["health_score"])
                total_alerts += dashboard["active_alerts"]
            
            num_instances = len(project_instances)
            print(f"  Instances: {num_instances}")
            print(f"  Avg Response Time: {avg_response_time/num_instances:.2f}s")
            print(f"  Avg Error Rate: {avg_error_rate/num_instances*100:.1f}%")
            print(f"  Min Health Score: {min_health:.1f}")
            print(f"  Total Active Alerts: {total_alerts}")
            print(f"  Estimated Cost: ${total_cost:.4f}")
        
        # System-wide monitoring view
        print("\n=== SYSTEM-WIDE MONITORING ===")
        
        # Get all active alerts
        all_alerts = await services["monitoring"].get_active_alerts()
        
        alert_by_type = {}
        for alert in all_alerts:
            alert_type = alert.alert_type.value
            alert_by_type[alert_type] = alert_by_type.get(alert_type, 0) + 1
        
        print(f"\nTotal Active Alerts: {len(all_alerts)}")
        for alert_type, count in alert_by_type.items():
            print(f"  {alert_type}: {count}")
        
        # Provider health across all instances
        provider_health = {"healthy": 0, "total": 0}
        for instance, _, _ in all_instances:
            health = await services["lifecycle"].check_instance_health(instance.id)
            provider_health["total"] += 1
            if health.checks.get("llm_providers_healthy", False):
                provider_health["healthy"] += 1
        
        print(f"\nLLM Provider Health: {provider_health['healthy']}/{provider_health['total']} instances healthy")
        
        # Query monitoring dashboard view
        result = await db.execute_query(
            """
            SELECT 
                COUNT(*) as total_instances,
                AVG(current_health_score) as avg_health,
                SUM(active_alerts) as total_alerts,
                SUM(current_spend_daily) as total_daily_spend
            FROM orchestrator.monitoring_dashboard
            """
        )
        
        if result and result[0]:
            stats = result[0]
            print(f"\nDatabase Dashboard View:")
            print(f"  Total Instances: {stats['total_instances']}")
            print(f"  Average Health: {stats['avg_health']:.1f}")
            print(f"  Total Alerts: {stats['total_alerts']}")
            print(f"  Total Daily Spend: ${stats['total_daily_spend']:.2f}")
        
        # Cleanup
        print("\nCleaning up...")
        for instance, _, _ in all_instances:
            await services["monitoring"].stop_monitoring(instance.id)
            await services["instance"].delete_instance(instance.id)