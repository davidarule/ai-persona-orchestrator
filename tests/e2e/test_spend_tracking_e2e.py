"""
End-to-end tests for Spend Tracking functionality
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal

from backend.services.spend_tracking_service import SpendTrackingService
from backend.services.persona_instance_service import PersonaInstanceService
from backend.services.llm_provider_service import LLMProviderService
from backend.factories.persona_instance_factory import PersonaInstanceFactory
from backend.models.persona_instance import LLMProvider, LLMModel
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.e2e
@pytest.mark.asyncio
class TestSpendTrackingE2E:
    """End-to-end tests simulating real-world spend tracking scenarios"""
    
    async def test_daily_team_operations_with_spend_tracking(
        self, db, azure_devops_config, clean_test_data
    ):
        """Test a full day of team operations with comprehensive spend tracking"""
        print("\n=== Daily Team Operations with Spend Tracking ===")
        
        # Initialize services
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        llm_service = LLMProviderService(db)
        await llm_service.initialize()
        
        try:
            # Create a development team
            print("\nStep 1: Creating development team...")
            factory = PersonaInstanceFactory(db)
            type_repo = PersonaTypeRepository(db)
            
            # Create persona types
            persona_types = {}
            for type_name, display, category in [
                ("lead-architect", "Lead Architect", PersonaCategory.ARCHITECTURE),
                ("senior-backend-dev", "Senior Backend Dev", PersonaCategory.DEVELOPMENT),
                ("frontend-dev", "Frontend Developer", PersonaCategory.DEVELOPMENT),
                ("qa-engineer", "QA Engineer", PersonaCategory.TESTING),
                ("devops-engineer", "DevOps Engineer", PersonaCategory.OPERATIONS)
            ]:
                persona_type = await type_repo.create(PersonaTypeCreate(
                    type_name=f"{type_name}-{uuid4().hex[:8]}",
                    display_name=display,
                    category=category,
                    description=f"{display} for daily operations",
                    base_workflow_id="wf0"
                ))
                persona_types[type_name] = persona_type
            
            # Create instances with appropriate budgets
            team = {}
            budgets = {
                "lead-architect": {"daily": Decimal("150.00"), "monthly": Decimal("3000.00")},
                "senior-backend-dev": {"daily": Decimal("100.00"), "monthly": Decimal("2000.00")},
                "frontend-dev": {"daily": Decimal("75.00"), "monthly": Decimal("1500.00")},
                "qa-engineer": {"daily": Decimal("50.00"), "monthly": Decimal("1000.00")},
                "devops-engineer": {"daily": Decimal("75.00"), "monthly": Decimal("1500.00")}
            }
            
            for role, persona_type in persona_types.items():
                instance = await factory.create_instance(
                    instance_name=f"TEST_{role.replace('-', '_')}_{uuid4().hex[:8]}",
                    persona_type_id=persona_type.id,
                    azure_devops_org=azure_devops_config["org_url"],
                    azure_devops_project=azure_devops_config["test_project"],
                    custom_spend_limits=budgets[role]
                )
                team[role] = instance
                print(f"  Created {role}: ${budgets[role]['daily']}/day budget")
            
            # Step 2: Simulate a day of work
            print("\nStep 2: Simulating daily operations...")
            
            daily_tasks = {
                "lead-architect": [
                    ("Morning architecture review", 2000, 1000, "gpt-4-turbo-preview"),
                    ("Design document creation", 4000, 2000, "gpt-4-turbo-preview"),
                    ("Code review assistance", 1500, 750, "gpt-4"),
                    ("Team consultation", 1000, 500, "gpt-4")
                ],
                "senior-backend-dev": [
                    ("API implementation", 2000, 1500, "gpt-4"),
                    ("Database optimization", 1500, 1000, "gpt-4"),
                    ("Code refactoring", 1000, 800, "gpt-3.5-turbo"),
                    ("Unit test creation", 800, 600, "gpt-3.5-turbo")
                ],
                "frontend-dev": [
                    ("Component development", 1500, 1200, "gpt-3.5-turbo"),
                    ("UI/UX improvements", 1000, 800, "gpt-3.5-turbo"),
                    ("Integration work", 800, 600, "gpt-3.5-turbo")
                ],
                "qa-engineer": [
                    ("Test case generation", 1000, 500, "gpt-3.5-turbo"),
                    ("Bug analysis", 800, 400, "gpt-3.5-turbo"),
                    ("Test automation", 600, 400, "gpt-3.5-turbo")
                ],
                "devops-engineer": [
                    ("Pipeline configuration", 1200, 800, "gpt-4"),
                    ("Infrastructure monitoring", 800, 400, "gpt-3.5-turbo"),
                    ("Deployment automation", 1000, 600, "gpt-3.5-turbo")
                ]
            }
            
            total_daily_cost = Decimal("0.00")
            
            for role, tasks in daily_tasks.items():
                instance = team[role]
                print(f"\n{role.replace('-', ' ').title()} tasks:")
                
                for task_name, input_tokens, output_tokens, model_name in tasks:
                    # Create LLM model
                    llm_model = LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name=model_name,
                        temperature=0.7,
                        api_key_env_var="OPENAI_API_KEY"
                    )
                    
                    # Record the spend
                    result = await spend_service.record_llm_spend(
                        instance_id=instance.id,
                        llm_model=llm_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        task_description=task_name
                    )
                    
                    total_daily_cost += result["cost"]
                    print(f"  - {task_name}: ${result['cost']:.3f}")
                    
                    # Check for warnings
                    if result["warnings"]:
                        for warning in result["warnings"]:
                            print(f"    ⚠️  {warning}")
                    
                    # Simulate time between tasks
                    await asyncio.sleep(0.1)
            
            print(f"\nTotal team cost for the day: ${total_daily_cost:.2f}")
            
            # Step 3: Check spend analytics
            print("\nStep 3: Analyzing team spend...")
            
            analytics = await spend_service.get_spend_analytics(
                project=azure_devops_config["test_project"]
            )
            
            print(f"\nTeam Analytics:")
            print(f"  Active instances: {analytics['summary']['instance_count']}")
            print(f"  Total daily spend: ${analytics['summary']['total_daily_spend']:.2f}")
            print(f"  Average daily spend: ${analytics['summary']['avg_daily_spend']:.2f}")
            print(f"  Daily utilization: {analytics['summary']['daily_utilization']:.1f}%")
            
            print("\nSpend by category:")
            for cat in analytics["by_category"]:
                print(f"  {cat['category']}: ${cat['total_amount']:.2f} "
                      f"({cat['transaction_count']} transactions)")
            
            print("\nTop spenders:")
            for i, spender in enumerate(analytics["top_spenders"][:3], 1):
                print(f"  {i}. {spender['name']}: ${spender['daily_spend']:.2f} "
                      f"({spender['daily_utilization']:.1f}% of limit)")
            
            # Step 4: Check for alerts
            print("\nStep 4: Checking spend alerts...")
            
            # Set alerts for high spenders
            for role, instance in team.items():
                await spend_service.set_spend_alerts(
                    instance_id=instance.id,
                    daily_threshold_pct=80,
                    monthly_threshold_pct=80
                )
            
            alerts = await spend_service.check_spend_alerts()
            if alerts:
                print(f"\n⚠️  {len(alerts)} instances have triggered alerts:")
                for alert in alerts:
                    print(f"  - {alert['instance_name']}:")
                    for a in alert["alerts"]:
                        print(f"    {a['type']}: {a['current_pct']:.1f}% of limit")
            else:
                print("  No alerts triggered")
            
            # Step 5: Project future costs
            print("\nStep 5: Projecting future costs...")
            
            for role, instance in list(team.items())[:2]:  # Just show top 2
                projections = await spend_service.get_cost_projections(instance.id)
                print(f"\n{role.replace('-', ' ').title()} projections:")
                print(f"  Projected daily average: ${projections['projected_daily_avg']:.2f}")
                print(f"  Projected monthly total: ${projections['projected_monthly_total']:.2f}")
                print(f"  Confidence: {projections['confidence']}")
            
            # Step 6: Optimize allocation
            print("\nStep 6: Optimizing budget allocation...")
            
            # Suggest optimization for a reduced budget
            current_total = sum(b["monthly"] for b in budgets.values())
            target_budget = current_total * Decimal("0.85")  # 15% reduction
            
            optimization = await spend_service.optimize_spend_allocation(
                project=azure_devops_config["test_project"],
                target_monthly_budget=target_budget
            )
            
            print(f"\nBudget optimization (reducing from ${current_total} to ${target_budget}):")
            print(f"  Current total: ${optimization['current_total_limit']:.2f}")
            print(f"  Target total: ${optimization['target_budget']:.2f}")
            
            print("\nRecommended changes:")
            for rec in optimization["recommendations"][:3]:  # Top 3 changes
                change_symbol = "↑" if rec["change_pct"] > 0 else "↓" if rec["change_pct"] < 0 else "→"
                print(f"  {rec['instance_name']}:")
                print(f"    Current: ${rec['current_limit']:.2f} → "
                      f"Suggested: ${rec['suggested_limit']:.2f} "
                      f"({change_symbol} {abs(rec['change_pct']):.1f}%)")
                print(f"    Reason: {rec['allocation_reason']}")
            
            print("\nDaily operations simulation complete!")
            
        finally:
            await spend_service.close()
            await llm_service.close()
    
    async def test_cost_overrun_scenario(self, db, clean_test_data):
        """Test handling of cost overrun scenarios"""
        print("\n=== Cost Overrun Scenario ===")
        
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        try:
            # Create a high-cost instance with low budget
            type_repo = PersonaTypeRepository(db)
            persona_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"ai-researcher-{uuid4().hex[:8]}",
                display_name="AI Researcher",
                category=PersonaCategory.SPECIALIZED,
                description="High-cost AI research tasks",
                base_workflow_id="wf0"
            ))
            
            factory = PersonaInstanceFactory(db)
            instance = await factory.create_instance(
                instance_name=f"TEST_Researcher_{uuid4().hex[:8]}",
                persona_type_id=persona_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="ResearchProject",
                custom_spend_limits={
                    "daily": Decimal("20.00"),  # Low daily limit
                    "monthly": Decimal("400.00")
                },
                custom_llm_providers=[
                    LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name="gpt-4-turbo-preview",  # Expensive model
                        temperature=0.7,
                        max_tokens=8192,
                        api_key_env_var="OPENAI_API_KEY"
                    )
                ]
            )
            
            print(f"Created researcher with ${20.00}/day budget using expensive models")
            
            # Set strict alerts
            await spend_service.set_spend_alerts(
                instance_id=instance.id,
                daily_threshold_pct=50,  # Alert at 50%
                monthly_threshold_pct=50
            )
            
            # Simulate research tasks
            print("\nSimulating research tasks...")
            
            research_tasks = [
                ("Literature review", 4000, 2000),
                ("Hypothesis generation", 3000, 1500),
                ("Data analysis", 5000, 2500),
                ("Report generation", 4000, 3000)
            ]
            
            for i, (task, input_tokens, output_tokens) in enumerate(research_tasks):
                print(f"\nTask {i+1}: {task}")
                
                # Check current status before task
                status_before = await spend_service.get_spend_status(instance.id)
                
                if status_before["daily_exceeded"]:
                    print(f"  ❌ Daily budget exceeded! Cannot proceed.")
                    print(f"     Current: ${status_before['daily_spent']:.2f} / "
                          f"${status_before['daily_limit']:.2f}")
                    break
                
                # Try to execute task
                try:
                    result = await spend_service.record_llm_spend(
                        instance_id=instance.id,
                        llm_model=instance.llm_providers[0],
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        task_description=task
                    )
                    
                    print(f"  ✓ Completed: ${result['cost']:.2f}")
                    print(f"    Daily remaining: ${result['daily_limit_remaining']:.2f}")
                    
                    if result["warnings"]:
                        for warning in result["warnings"]:
                            print(f"    ⚠️  {warning}")
                    
                except Exception as e:
                    print(f"  ❌ Failed: {str(e)}")
            
            # Final status
            final_status = await spend_service.get_spend_status(instance.id)
            print(f"\nFinal status:")
            print(f"  Daily: ${final_status['daily_spent']:.2f} / "
                  f"${final_status['daily_limit']:.2f} "
                  f"({final_status['daily_percentage']:.1f}%)")
            
            # Check alerts
            alerts = await spend_service.check_spend_alerts()
            if alerts:
                print(f"\n⚠️  Alerts triggered for cost overrun")
            
        finally:
            await spend_service.close()
    
    async def test_monthly_budget_cycle(self, db, clean_test_data):
        """Test monthly budget cycle with resets"""
        print("\n=== Monthly Budget Cycle Simulation ===")
        
        spend_service = SpendTrackingService(db)
        await spend_service.initialize()
        
        instance_service = PersonaInstanceService(db)
        
        try:
            # Create instance
            type_repo = PersonaTypeRepository(db)
            persona_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"monthly-worker-{uuid4().hex[:8]}",
                display_name="Monthly Worker",
                category=PersonaCategory.DEVELOPMENT,
                description="Test monthly cycles",
                base_workflow_id="wf0"
            ))
            
            factory = PersonaInstanceFactory(db)
            instance = await factory.create_instance(
                instance_name=f"TEST_Monthly_{uuid4().hex[:8]}",
                persona_type_id=persona_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="MonthlyTest",
                custom_spend_limits={
                    "daily": Decimal("50.00"),
                    "monthly": Decimal("1000.00")
                }
            )
            
            print("Simulating 5 days of work...")
            
            # Simulate 5 days
            for day in range(5):
                print(f"\nDay {day + 1}:")
                
                # Daily work
                daily_cost = Decimal("0.00")
                for task in range(3):
                    result = await spend_service.record_llm_spend(
                        instance_id=instance.id,
                        llm_model=LLMModel(
                            provider=LLMProvider.OPENAI,
                            model_name="gpt-3.5-turbo",
                            api_key_env_var="OPENAI_API_KEY"
                        ),
                        input_tokens=500,
                        output_tokens=250,
                        task_description=f"Day {day+1} Task {task+1}"
                    )
                    daily_cost += result["cost"]
                
                print(f"  Daily cost: ${daily_cost:.2f}")
                
                # End of day - reset daily spend
                if day < 4:  # Don't reset on last day
                    print("  Resetting daily spend...")
                    await instance_service.reset_daily_spend_all()
            
            # Check final status
            status = await spend_service.get_spend_status(instance.id)
            print(f"\nAfter 5 days:")
            print(f"  Monthly spend: ${status['monthly_spent']:.2f} / "
                  f"${status['monthly_limit']:.2f}")
            print(f"  Daily spend (current): ${status['daily_spent']:.2f} / "
                  f"${status['daily_limit']:.2f}")
            
            # Simulate month end
            print("\nSimulating month end...")
            await instance_service.reset_monthly_spend_all()
            
            status_after_reset = await spend_service.get_spend_status(instance.id)
            print(f"After monthly reset:")
            print(f"  Monthly spend: ${status_after_reset['monthly_spent']:.2f}")
            print(f"  Daily spend: ${status_after_reset['daily_spent']:.2f}")
            
        finally:
            await spend_service.close()