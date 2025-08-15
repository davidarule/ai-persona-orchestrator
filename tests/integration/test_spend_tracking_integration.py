"""
Integration tests for Spend Tracking functionality
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal

from backend.services.spend_tracking_service import SpendTrackingService
from backend.services.persona_instance_service import PersonaInstanceService
from backend.models.persona_instance import (
    PersonaInstanceCreate, LLMProvider, LLMModel
)
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.integration
@pytest.mark.asyncio
class TestSpendTrackingIntegration:
    """Integration tests for spend tracking with multiple services"""
    
    async def test_spend_tracking_with_persona_service(self, db, clean_test_data):
        """Test spend tracking integrated with persona instance service"""
        # Create persona type
        type_repo = PersonaTypeRepository(db)
        persona_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"developer-{uuid4().hex[:8]}",
            display_name="Developer",
            category=PersonaCategory.DEVELOPMENT,
            description="Test developer",
            base_workflow_id="wf0"
        ))
        
        # Create instance
        instance_service = PersonaInstanceService(db)
        instance = await instance_service.create_instance(PersonaInstanceCreate(
            instance_name=f"TEST_Dev_{uuid4().hex[:8]}",
            persona_type_id=persona_type.id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="TestProject",
            spend_limit_daily=Decimal("50.00"),
            spend_limit_monthly=Decimal("1000.00")
        ))
        
        # Initialize spend tracking
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        try:
            # Record some LLM usage
            llm_model = LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                api_key_env_var="OPENAI_API_KEY"
            )
            
            for i in range(5):
                result = await spend_service.record_llm_spend(
                    instance_id=instance.id,
                    llm_model=llm_model,
                    input_tokens=500,
                    output_tokens=250,
                    task_description=f"Development task {i}"
                )
                
                # Also record through instance service
                await instance_service.record_spend(
                    instance.id,
                    result["cost"],
                    f"Task {i} via instance service"
                )
            
            # Verify spend is tracked correctly
            status = await spend_service.get_spend_status(instance.id)
            assert status["daily_spent"] > Decimal("0")
            
            # Check instance service also sees the spend
            updated_instance = await instance_service.get_instance(instance.id)
            assert updated_instance.current_spend_daily > Decimal("0")
            assert updated_instance.spend_percentage_daily > 0
            
        finally:
            await spend_service.close()
    
    async def test_multi_instance_spend_analytics(self, db, azure_devops_config, clean_test_data):
        """Test analytics across multiple instances"""
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        type_repo = PersonaTypeRepository(db)
        instance_service = PersonaInstanceService(db)
        
        try:
            # Create instances of different types
            instance_ids = []
            
            for category, name in [
                (PersonaCategory.ARCHITECTURE, "Architect"),
                (PersonaCategory.DEVELOPMENT, "Developer"), 
                (PersonaCategory.TESTING, "Tester")
            ]:
                # Create type
                persona_type = await type_repo.create(PersonaTypeCreate(
                    type_name=f"{name.lower()}-{uuid4().hex[:8]}",
                    display_name=name,
                    category=category,
                    description=f"Test {name}",
                    base_workflow_id="wf0"
                ))
                
                # Create instance
                instance = await instance_service.create_instance(PersonaInstanceCreate(
                    instance_name=f"TEST_{name}_{uuid4().hex[:8]}",
                    persona_type_id=persona_type.id,
                    azure_devops_org=azure_devops_config["org_url"],
                    azure_devops_project=azure_devops_config["test_project"],
                    spend_limit_daily=Decimal("100.00"),
                    spend_limit_monthly=Decimal("2000.00")
                ))
                instance_ids.append(instance.id)
                
                # Record varying amounts of spend
                for i in range(3):
                    await spend_service.record_llm_spend(
                        instance_id=instance.id,
                        llm_model=LLMModel(
                            provider=LLMProvider.OPENAI,
                            model_name="gpt-4" if category == PersonaCategory.ARCHITECTURE else "gpt-3.5-turbo",
                            api_key_env_var="OPENAI_API_KEY"
                        ),
                        input_tokens=1000 * (i + 1),
                        output_tokens=500 * (i + 1),
                        task_description=f"{name} task {i}"
                    )
            
            # Get analytics for the project
            analytics = await spend_service.get_spend_analytics(
                project=azure_devops_config["test_project"]
            )
            
            assert analytics["summary"]["instance_count"] == 3
            assert analytics["summary"]["total_daily_spend"] > 0
            assert len(analytics["by_category"]) > 0
            assert len(analytics["top_spenders"]) == 3
            
            # Get analytics by persona type
            architect_type_id = None
            types = await type_repo.list_all()
            for t in types:
                if t.category == PersonaCategory.ARCHITECTURE:
                    architect_type_id = t.id
                    break
            
            if architect_type_id:
                type_analytics = await spend_service.get_spend_analytics(
                    persona_type_id=architect_type_id
                )
                assert type_analytics["summary"]["instance_count"] == 1
            
        finally:
            await spend_service.close()
    
    async def test_spend_alerts_workflow(self, db, clean_test_data):
        """Test complete spend alert workflow"""
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        try:
            # Create test instance
            type_repo = PersonaTypeRepository(db)
            persona_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"alerter-{uuid4().hex[:8]}",
                display_name="Alert Tester",
                category=PersonaCategory.OPERATIONS,
                description="Test alerts",
                base_workflow_id="wf0"
            ))
            
            instance_service = PersonaInstanceService(db)
            instance = await instance_service.create_instance(PersonaInstanceCreate(
                instance_name=f"TEST_Alerter_{uuid4().hex[:8]}",
                persona_type_id=persona_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="AlertTest",
                spend_limit_daily=Decimal("10.00"),  # Low limit for easy testing
                spend_limit_monthly=Decimal("200.00")
            ))
            
            # Set custom alert thresholds
            await spend_service.set_spend_alerts(
                instance_id=instance.id,
                daily_threshold_pct=50,  # Alert at 50%
                monthly_threshold_pct=50
            )
            
            # Record spend to trigger alerts
            for i in range(3):
                await spend_service.record_llm_spend(
                    instance_id=instance.id,
                    llm_model=LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name="gpt-3.5-turbo",
                        api_key_env_var="OPENAI_API_KEY"
                    ),
                    input_tokens=1000,
                    output_tokens=500,
                    task_description=f"Task triggering alert {i}"
                )
            
            # Check for alerts
            alerts = await spend_service.check_spend_alerts()
            
            # Should have alerts for our instance
            instance_alerts = [a for a in alerts if a["instance_id"] == str(instance.id)]
            assert len(instance_alerts) > 0
            
            alert = instance_alerts[0]
            assert len(alert["alerts"]) > 0
            assert any(a["type"] == "daily_threshold" for a in alert["alerts"])
            
        finally:
            await spend_service.close()
    
    async def test_spend_optimization_scenario(self, db, azure_devops_config, clean_test_data):
        """Test realistic spend optimization scenario"""
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        try:
            # Create a team with unbalanced spend
            type_repo = PersonaTypeRepository(db)
            instance_service = PersonaInstanceService(db)
            
            team_config = [
                ("architect", PersonaCategory.ARCHITECTURE, Decimal("200.00"), 0.95),  # Over-utilized
                ("senior_dev", PersonaCategory.DEVELOPMENT, Decimal("150.00"), 0.80),  # Well utilized
                ("junior_dev", PersonaCategory.DEVELOPMENT, Decimal("100.00"), 0.20),  # Under-utilized
                ("qa_lead", PersonaCategory.TESTING, Decimal("100.00"), 0.90),        # Near limit
                ("devops", PersonaCategory.OPERATIONS, Decimal("150.00"), 0.10)       # Very under-utilized
            ]
            
            instances = []
            
            for role, category, monthly_limit, utilization in team_config:
                # Create type
                persona_type = await type_repo.create(PersonaTypeCreate(
                    type_name=f"{role}-{uuid4().hex[:8]}",
                    display_name=role.replace("_", " ").title(),
                    category=category,
                    description=f"Test {role}",
                    base_workflow_id="wf0"
                ))
                
                # Create instance
                instance = await instance_service.create_instance(PersonaInstanceCreate(
                    instance_name=f"TEST_{role}_{uuid4().hex[:8]}",
                    persona_type_id=persona_type.id,
                    azure_devops_org=azure_devops_config["org_url"],
                    azure_devops_project="OptimizationTest",
                    spend_limit_daily=monthly_limit / 30,
                    spend_limit_monthly=monthly_limit
                ))
                
                # Simulate historical spend to match utilization
                current_spend = monthly_limit * Decimal(str(utilization))
                await db.execute_query(
                    """
                    UPDATE orchestrator.persona_instances
                    SET current_spend_monthly = $2
                    WHERE id = $1
                    """,
                    instance.id,
                    current_spend
                )
                
                instances.append(instance.id)
            
            # Get optimization recommendations
            optimization = await spend_service.optimize_spend_allocation(
                project="OptimizationTest",
                target_monthly_budget=Decimal("600.00")  # Reduce from 700 to 600
            )
            
            assert optimization["current_total_limit"] == 700.0
            assert optimization["target_budget"] == 600.0
            assert len(optimization["recommendations"]) == 5
            
            # Check recommendations make sense
            for rec in optimization["recommendations"]:
                if "Over-utilized" in rec["allocation_reason"] or "at capacity" in rec["allocation_reason"]:
                    # Should suggest increase or maintain
                    assert rec["change_pct"] >= -10  # Max 10% decrease
                elif "Under-utilized" in rec["allocation_reason"] or "Low utilization" in rec["allocation_reason"]:
                    # Should suggest decrease
                    assert rec["change_pct"] < 0
            
        finally:
            await spend_service.close()
    
    async def test_historical_projections(self, db, clean_test_data):
        """Test cost projections based on historical data"""
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        try:
            # Create instance
            type_repo = PersonaTypeRepository(db)
            persona_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"predictor-{uuid4().hex[:8]}",
                display_name="Predictor",
                category=PersonaCategory.SPECIALIZED,
                description="Test predictions",
                base_workflow_id="wf0"
            ))
            
            instance_service = PersonaInstanceService(db)
            instance = await instance_service.create_instance(PersonaInstanceCreate(
                instance_name=f"TEST_Predictor_{uuid4().hex[:8]}",
                persona_type_id=persona_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="PredictionTest",
                spend_limit_monthly=Decimal("1000.00")
            ))
            
            # Simulate 15 days of historical data with pattern
            base_date = datetime.utcnow() - timedelta(days=15)
            
            for day in range(15):
                date = base_date + timedelta(days=day)
                
                # Weekday vs weekend pattern
                is_weekend = date.weekday() >= 5
                daily_base = Decimal("20.00") if not is_weekend else Decimal("5.00")
                
                # Add some variance
                variance = Decimal(str(day % 3))
                daily_spend = daily_base + variance
                
                # Record multiple transactions per day
                for i in range(3 if not is_weekend else 1):
                    await spend_service._record_spend_detail(
                        instance_id=instance.id,
                        amount=daily_spend / 3,
                        category="llm_usage",
                        description=f"Historical task day {day} task {i}",
                        metadata={"date": date.isoformat(), "is_weekend": is_weekend}
                    )
            
            # Get projections
            projections = await spend_service.get_cost_projections(instance.id)
            
            assert projections["confidence"] == "medium"  # 15 days of data
            assert projections["based_on_days"] == 15
            assert projections["projected_daily_avg"] > 0
            assert projections["projected_monthly_total"] > 0
            
            # Historical stats should show variance
            assert projections["historical_daily_min"] < projections["historical_daily_max"]
            
        finally:
            await spend_service.close()