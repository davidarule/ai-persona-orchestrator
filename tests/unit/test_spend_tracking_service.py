"""
Unit tests for Spend Tracking Service
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import json

from backend.services.spend_tracking_service import SpendTrackingService
from backend.models.persona_instance import LLMProvider, LLMModel


@pytest.mark.asyncio
class TestSpendTrackingService:
    """Test Spend Tracking Service functionality"""
    
    @pytest.fixture
    async def service(self, db):
        """Create SpendTrackingService instance"""
        service = SpendTrackingService(db)
        await service.initialize()
        yield service
        await service.close()
    
    async def test_record_llm_spend(self, service, test_persona_instance_id):
        """Test recording LLM usage and spend"""
        # Setup test data
        llm_model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4",
            temperature=0.7,
            api_key_env_var="OPENAI_API_KEY"
        )
        
        # Record spend
        result = await service.record_llm_spend(
            instance_id=test_persona_instance_id,
            llm_model=llm_model,
            input_tokens=1000,
            output_tokens=500,
            task_description="Test task",
            success=True
        )
        
        # Verify result
        assert "cost" in result
        assert "daily_limit_remaining" in result
        assert "monthly_limit_remaining" in result
        assert "warnings" in result
        
        # GPT-4: $30/1M input, $60/1M output
        expected_cost = Decimal("0.030") + Decimal("0.030")  # $0.060
        assert result["cost"] == expected_cost
    
    async def test_record_api_spend(self, service, test_persona_instance_id):
        """Test recording API usage spend"""
        result = await service.record_api_spend(
            instance_id=test_persona_instance_id,
            api_name="Azure DevOps",
            operation="Create Work Item",
            cost=Decimal("0.01"),
            request_count=1
        )
        
        assert result["cost"] == Decimal("0.01")
        assert "daily_limit_remaining" in result
        assert "monthly_limit_remaining" in result
    
    async def test_get_spend_status(self, service, test_persona_instance_id):
        """Test getting current spend status"""
        status = await service.get_spend_status(test_persona_instance_id)
        
        assert "daily_spent" in status
        assert "daily_limit" in status
        assert "daily_remaining" in status
        assert "daily_percentage" in status
        assert "monthly_spent" in status
        assert "monthly_limit" in status
        assert "monthly_remaining" in status
        assert "monthly_percentage" in status
        assert "daily_exceeded" in status
        assert "monthly_exceeded" in status
    
    async def test_spend_warnings(self, service, test_persona_instance_id):
        """Test spend warning generation"""
        # First, update instance to have high spend
        update_query = """
        UPDATE orchestrator.persona_instances
        SET 
            current_spend_daily = spend_limit_daily * 0.85,
            current_spend_monthly = spend_limit_monthly * 0.85
        WHERE id = $1
        """
        await service.db.execute_query(update_query, test_persona_instance_id)
        
        # Record small additional spend
        llm_model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-3.5-turbo",
            api_key_env_var="OPENAI_API_KEY"
        )
        
        result = await service.record_llm_spend(
            instance_id=test_persona_instance_id,
            llm_model=llm_model,
            input_tokens=100,
            output_tokens=50,
            task_description="Small task"
        )
        
        # Should have warnings
        assert len(result["warnings"]) > 0
        assert any("Daily spend" in w for w in result["warnings"])
        assert any("Monthly spend" in w for w in result["warnings"])
    
    async def test_get_spend_history(self, service, test_persona_instance_id):
        """Test retrieving spend history"""
        # Add some spend records
        for i in range(5):
            await service.record_api_spend(
                instance_id=test_persona_instance_id,
                api_name="Test API",
                operation=f"Operation {i}",
                cost=Decimal("1.00"),
                request_count=1
            )
        
        # Get history
        history = await service.get_spend_history(test_persona_instance_id)
        
        assert len(history) >= 5
        assert all(isinstance(record["amount"], Decimal) for record in history)
        assert all("category" in record for record in history)
        assert all("description" in record for record in history)
    
    async def test_get_spend_analytics(self, service, db, test_persona_instance_id):
        """Test spend analytics generation"""
        # Add some spend data
        for i in range(3):
            await service.record_llm_spend(
                instance_id=test_persona_instance_id,
                llm_model=LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                ),
                input_tokens=1000,
                output_tokens=500,
                task_description=f"Task {i}"
            )
        
        # Get analytics
        analytics = await service.get_spend_analytics()
        
        assert "summary" in analytics
        assert analytics["summary"]["instance_count"] > 0
        assert "by_category" in analytics
        assert "top_spenders" in analytics
    
    async def test_cost_projections(self, service, test_persona_instance_id):
        """Test cost projection calculations"""
        # Add historical data
        for day in range(10):
            date = datetime.utcnow() - timedelta(days=day)
            # Simulate varying daily costs
            daily_cost = Decimal("10.00") + Decimal(str(day % 3))
            
            await service._record_spend_detail(
                instance_id=test_persona_instance_id,
                amount=daily_cost,
                category="llm_usage",
                description=f"Historical day {day}",
                metadata={"date": date.isoformat()}
            )
        
        # Get projections
        projections = await service.get_cost_projections(test_persona_instance_id)
        
        assert projections["confidence"] in ["low", "medium", "high"]
        assert projections["projected_daily_avg"] > 0
        assert projections["projected_monthly_total"] > 0
        assert projections["based_on_days"] > 0
    
    async def test_set_and_check_alerts(self, service, test_persona_instance_id):
        """Test setting and checking spend alerts"""
        # Set alerts
        await service.set_spend_alerts(
            instance_id=test_persona_instance_id,
            daily_threshold_pct=75,
            monthly_threshold_pct=75
        )
        
        # Update instance to trigger alert
        update_query = """
        UPDATE orchestrator.persona_instances
        SET 
            current_spend_daily = spend_limit_daily * 0.76,
            current_spend_monthly = spend_limit_monthly * 0.76
        WHERE id = $1
        """
        await service.db.execute_query(update_query, test_persona_instance_id)
        
        # Check alerts
        alerts = await service.check_spend_alerts()
        
        # Should find our instance with alerts
        instance_alert = next(
            (a for a in alerts if a["instance_id"] == str(test_persona_instance_id)),
            None
        )
        
        assert instance_alert is not None
        assert len(instance_alert["alerts"]) > 0
    
    async def test_optimize_spend_allocation(self, service, db, azure_devops_config):
        """Test spend allocation optimization"""
        # Create multiple instances in same project
        instances = []
        
        for i in range(3):
            # Create persona type
            type_query = """
            INSERT INTO orchestrator.persona_types (
                type_name, display_name, base_workflow_id
            ) VALUES ($1, $2, $3)
            RETURNING id
            """
            type_result = await db.execute_query(
                type_query,
                f"test-type-{i}-{uuid4().hex[:8]}",
                f"Test Type {i}",
                "wf0",
                fetch_one=True
            )
            
            # Create instance
            instance_query = """
            INSERT INTO orchestrator.persona_instances (
                instance_name, persona_type_id, azure_devops_org, 
                azure_devops_project, spend_limit_monthly, current_spend_monthly
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """
            
            spend_limit = Decimal("100.00") * (i + 1)  # Varying limits
            current_spend = spend_limit * Decimal("0.5") * (i + 1) / 3  # Varying usage
            
            instance_result = await db.execute_query(
                instance_query,
                f"TEST_Instance_{i}_{uuid4().hex[:8]}",
                type_result["id"],
                azure_devops_config["org_url"],
                azure_devops_config["test_project"],
                spend_limit,
                current_spend,
                fetch_one=True
            )
            instances.append(instance_result["id"])
        
        # Optimize allocation
        optimization = await service.optimize_spend_allocation(
            project=azure_devops_config["test_project"],
            target_monthly_budget=Decimal("500.00")
        )
        
        assert "recommendations" in optimization
        assert len(optimization["recommendations"]) == len(instances)
        assert optimization["target_budget"] == 500.0
        
        # Clean up
        for instance_id in instances:
            await db.execute_query(
                "DELETE FROM orchestrator.persona_instances WHERE id = $1",
                instance_id
            )
    
    async def test_spend_tracking_with_metadata(self, service, test_persona_instance_id):
        """Test spend tracking with detailed metadata"""
        metadata = {
            "workflow_id": "wf0",
            "task_id": "task-123",
            "azure_devops_work_item": 456,
            "execution_time_ms": 2500
        }
        
        await service._record_spend_detail(
            instance_id=test_persona_instance_id,
            amount=Decimal("5.00"),
            category="workflow_execution",
            description="Complex workflow task",
            metadata=metadata
        )
        
        # Retrieve and verify
        history = await service.get_spend_history(
            test_persona_instance_id,
            category="workflow_execution"
        )
        
        assert len(history) > 0
        latest = history[0]
        assert latest["metadata"]["workflow_id"] == "wf0"
        assert latest["metadata"]["task_id"] == "task-123"
    
    async def test_concurrent_spend_updates(self, service, test_persona_instance_id):
        """Test concurrent spend updates don't cause issues"""
        import asyncio
        
        async def record_spend(index):
            await service.record_api_spend(
                instance_id=test_persona_instance_id,
                api_name="Test API",
                operation=f"Concurrent Op {index}",
                cost=Decimal("1.00")
            )
        
        # Run 10 concurrent updates
        tasks = [record_spend(i) for i in range(10)]
        await asyncio.gather(*tasks)
        
        # Verify total
        status = await service.get_spend_status(test_persona_instance_id)
        
        # Should have recorded all 10
        assert status["daily_spent"] >= Decimal("10.00")