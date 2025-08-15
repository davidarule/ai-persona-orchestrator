"""
End-to-End tests for LLM Fallback Chain
Real-world scenarios with multiple providers and failure conditions
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal
import random

from backend.services.llm_fallback_chain import (
    LLMFallbackChain,
    LLMRequest,
    RoutingStrategy
)
from backend.services.persona_instance_lifecycle import PersonaInstanceLifecycle, InstanceState
from backend.services.persona_instance_service import PersonaInstanceService
from backend.factories.persona_instance_factory import PersonaInstanceFactory
from backend.models.persona_instance import PersonaInstanceCreate, LLMProvider, LLMModel
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.e2e
@pytest.mark.asyncio
class TestLLMFallbackChainE2E:
    """E2E tests simulating real-world LLM usage scenarios"""
    
    @pytest.fixture
    async def services(self, db):
        """Create all required services"""
        fallback = LLMFallbackChain(db)
        lifecycle = PersonaInstanceLifecycle(db)
        instance_service = PersonaInstanceService(db)
        
        await fallback.initialize()
        await lifecycle.initialize()
        
        yield {
            "fallback": fallback,
            "lifecycle": lifecycle,
            "instance": instance_service
        }
        
        await fallback.close()
        await lifecycle.close()
    
    @pytest.fixture
    async def test_persona_types(self, db):
        """Create test persona types"""
        repo = PersonaTypeRepository(db)
        types = {}
        
        for name, display in [
            ("developer", "Developer"),
            ("architect", "Architect"),
            ("qa", "QA Engineer")
        ]:
            persona_type = await repo.create(PersonaTypeCreate(
                type_name=f"{name}-e2e-fallback-{uuid4().hex[:8]}",
                display_name=f"E2E {display}",
                category=PersonaCategory.DEVELOPMENT,
                description=f"E2E test {display}",
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
    
    async def test_development_team_with_provider_outages(self, services, test_persona_types, azure_devops_config):
        """Test development team handling provider outages gracefully"""
        print("\n=== DEVELOPMENT TEAM WITH PROVIDER OUTAGES ===")
        
        # Create team with diverse LLM configurations
        team_configs = [
            {
                "name": "Senior Dev",
                "type": "developer",
                "providers": [
                    LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-4", api_key_env_var="OPENAI_API_KEY"),
                    LLMModel(provider=LLMProvider.ANTHROPIC, model_name="claude-2", api_key_env_var="ANTHROPIC_API_KEY"),
                    LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-3.5-turbo", api_key_env_var="OPENAI_API_KEY")
                ]
            },
            {
                "name": "Architect",
                "type": "architect",
                "providers": [
                    LLMModel(provider=LLMProvider.ANTHROPIC, model_name="claude-2", api_key_env_var="ANTHROPIC_API_KEY"),
                    LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-4", api_key_env_var="OPENAI_API_KEY")
                ]
            },
            {
                "name": "QA Engineer",
                "type": "qa",
                "providers": [
                    LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-3.5-turbo", api_key_env_var="OPENAI_API_KEY"),
                    LLMModel(provider=LLMProvider.GEMINI, model_name="gemini-pro", api_key_env_var="GEMINI_API_KEY")
                ]
            }
        ]
        
        team_instances = []
        
        # Create team instances
        for config in team_configs:
            instance = await services["instance"].create_instance(PersonaInstanceCreate(
                instance_name=f"{config['name']}-{uuid4().hex[:8]}",
                persona_type_id=test_persona_types[config["type"]].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project="ProviderOutageTest",
                llm_providers=config["providers"],
                spend_limit_daily=Decimal("100.00"),
                spend_limit_monthly=Decimal("2000.00")
            ))
            team_instances.append(instance)
            
            # Initialize lifecycle
            await services["lifecycle"].provision_instance(instance.id)
        
        print("✓ Team created with fallback configurations")
        
        # Simulate provider outages
        outage_scenarios = [
            {"provider": LLMProvider.OPENAI, "duration": 5, "reason": "Rate limit"},
            {"provider": LLMProvider.ANTHROPIC, "duration": 3, "reason": "Service degradation"},
            {"provider": LLMProvider.GEMINI, "duration": 2, "reason": "Authentication issue"}
        ]
        
        # Mock API calls with outage simulation
        outage_times = {}
        for scenario in outage_scenarios:
            outage_times[scenario["provider"]] = {
                "start": datetime.utcnow(),
                "end": datetime.utcnow() + timedelta(minutes=scenario["duration"])
            }
        
        async def mock_api_with_outages(provider, request):
            # Check if provider is experiencing outage
            if provider.provider in outage_times:
                outage = outage_times[provider.provider]
                if outage["start"] <= datetime.utcnow() <= outage["end"]:
                    raise Exception(f"{provider.provider} experiencing outage")
            
            # Otherwise return success
            return {
                "content": f"Response from {provider.model_name}: Processed request successfully",
                "input_tokens": 50,
                "output_tokens": 100
            }
        
        services["fallback"]._call_provider_api = mock_api_with_outages
        
        # Simulate work requests during outages
        print("\nPhase 1: Normal Operations")
        
        for i, instance in enumerate(team_instances):
            request = LLMRequest(
                instance_id=instance.id,
                prompt=f"Implement a function to {['parse JSON', 'validate input', 'run tests'][i]}",
                max_tokens=200,
                temperature=0.7
            )
            
            try:
                response = await services["fallback"].execute_request(
                    request,
                    instance.llm_providers,
                    RoutingStrategy.PRIORITY
                )
                print(f"✓ {team_configs[i]['name']}: Success with {response.provider} ({response.model})")
            except Exception as e:
                print(f"✗ {team_configs[i]['name']}: Failed - {e}")
        
        # Simulate OpenAI outage
        print("\nPhase 2: OpenAI Outage")
        
        for i, instance in enumerate(team_instances):
            request = LLMRequest(
                instance_id=instance.id,
                prompt="Continue with the implementation",
                max_tokens=150
            )
            
            response = await services["fallback"].execute_request(
                request,
                instance.llm_providers,
                RoutingStrategy.PRIORITY
            )
            
            if response.fallback_used:
                print(f"✓ {team_configs[i]['name']}: Fallback to {response.provider} ({response.model})")
            else:
                print(f"✓ {team_configs[i]['name']}: Primary provider {response.provider} still working")
        
        # Check health report
        print("\nPhase 3: Provider Health Report")
        health_report = await services["fallback"].get_provider_health_report()
        
        for provider_name, health in health_report["providers"].items():
            status = "🟢" if health["healthy"] else "🔴"
            print(f"{status} {provider_name}: {health['success_rate']*100:.1f}% success rate, "
                  f"{health['total_requests']} requests")
        
        # Cleanup
        for instance in team_instances:
            await services["lifecycle"].terminate_instance(instance.id, "Test complete", force=True)
            await asyncio.sleep(0.1)
            await services["instance"].delete_instance(instance.id)
    
    async def test_cost_optimization_scenario(self, services, test_persona_types, azure_devops_config):
        """Test cost optimization across multiple instances"""
        print("\n=== COST OPTIMIZATION SCENARIO ===")
        
        # Create instances with varying budget constraints
        budget_tiers = [
            {"name": "Premium", "daily": "200.00", "strategy": RoutingStrategy.PRIORITY},
            {"name": "Standard", "daily": "50.00", "strategy": RoutingStrategy.LEAST_COST},
            {"name": "Budget", "daily": "10.00", "strategy": RoutingStrategy.LEAST_COST}
        ]
        
        instances = []
        
        for tier in budget_tiers:
            instance = await services["instance"].create_instance(PersonaInstanceCreate(
                instance_name=f"{tier['name']}-Instance-{uuid4().hex[:8]}",
                persona_type_id=test_persona_types["developer"].id,
                azure_devops_org=azure_devops_config["org_url"],
                azure_devops_project="CostOptimizationTest",
                llm_providers=[
                    LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-4", api_key_env_var="OPENAI_API_KEY"),
                    LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-3.5-turbo", api_key_env_var="OPENAI_API_KEY"),
                    LLMModel(provider=LLMProvider.ANTHROPIC, model_name="claude-instant", api_key_env_var="ANTHROPIC_API_KEY")
                ],
                spend_limit_daily=Decimal(tier["daily"]),
                spend_limit_monthly=Decimal(tier["daily"]) * 30
            ))
            instances.append((tier, instance))
            await services["lifecycle"].provision_instance(instance.id)
        
        # Mock API with cost tracking
        async def mock_api_with_costs(provider, request):
            costs = {
                "gpt-4": 0.03,
                "gpt-3.5-turbo": 0.002,
                "claude-instant": 0.008
            }
            
            return {
                "content": f"{provider.model_name} response",
                "input_tokens": 100,
                "output_tokens": 200,
                "cost": costs.get(provider.model_name, 0.01)
            }
        
        services["fallback"]._call_provider_api = mock_api_with_costs
        
        # Simulate multiple requests
        print("\nProcessing requests with different budget tiers:")
        
        for tier_config, instance in instances:
            total_cost = 0.0
            models_used = []
            
            for i in range(5):
                request = LLMRequest(
                    instance_id=instance.id,
                    prompt=f"Task {i+1}: Analyze code complexity",
                    max_tokens=150
                )
                
                response = await services["fallback"].execute_request(
                    request,
                    instance.llm_providers,
                    tier_config["strategy"]
                )
                
                total_cost += response.cost
                models_used.append(response.model)
            
            print(f"\n{tier_config['name']} Tier (${tier_config['daily']}/day):")
            print(f"  Models used: {', '.join(set(models_used))}")
            print(f"  Total cost: ${total_cost:.3f}")
            print(f"  Average cost per request: ${total_cost/5:.3f}")
        
        # Cleanup
        for _, instance in instances:
            await services["instance"].delete_instance(instance.id)
    
    async def test_high_availability_with_circuit_breakers(self, services, test_persona_types, azure_devops_config):
        """Test high availability with circuit breakers and recovery"""
        print("\n=== HIGH AVAILABILITY WITH CIRCUIT BREAKERS ===")
        
        # Create critical production instance
        prod_instance = await services["instance"].create_instance(PersonaInstanceCreate(
            instance_name=f"Production-Critical-{uuid4().hex[:8]}",
            persona_type_id=test_persona_types["architect"].id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="ProductionHA",
            llm_providers=[
                LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-4", api_key_env_var="OPENAI_API_KEY"),
                LLMModel(provider=LLMProvider.ANTHROPIC, model_name="claude-2", api_key_env_var="ANTHROPIC_API_KEY"),
                LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-3.5-turbo", api_key_env_var="OPENAI_API_KEY"),
                LLMModel(provider=LLMProvider.GEMINI, model_name="gemini-pro", api_key_env_var="GEMINI_API_KEY")
            ],
            spend_limit_daily=Decimal("500.00"),
            spend_limit_monthly=Decimal("10000.00"),
            priority_level=10  # Maximum priority
        ))
        
        await services["lifecycle"].provision_instance(prod_instance.id)
        
        # Configure aggressive circuit breaker settings
        services["fallback"].circuit_breaker_threshold = 3
        services["fallback"].circuit_breaker_timeout = timedelta(minutes=2)
        
        # Simulate provider instability
        provider_failure_patterns = {
            LLMProvider.OPENAI: {"failure_rate": 0.4, "pattern": "intermittent"},
            LLMProvider.ANTHROPIC: {"failure_rate": 0.2, "pattern": "burst"},
            LLMProvider.GEMINI: {"failure_rate": 0.6, "pattern": "degraded"}
        }
        
        request_count = 0
        burst_failure_window = (10, 15)  # Burst failures between requests 10-15
        
        async def mock_unstable_api(provider, request):
            nonlocal request_count
            request_count += 1
            
            pattern = provider_failure_patterns.get(
                provider.provider, 
                {"failure_rate": 0.1, "pattern": "stable"}
            )
            
            # Apply failure patterns
            should_fail = False
            
            if pattern["pattern"] == "intermittent":
                should_fail = random.random() < pattern["failure_rate"]
            elif pattern["pattern"] == "burst":
                should_fail = (burst_failure_window[0] <= request_count <= burst_failure_window[1])
            elif pattern["pattern"] == "degraded":
                should_fail = random.random() < pattern["failure_rate"]
            
            if should_fail:
                raise Exception(f"{provider.provider} temporary failure")
            
            return {
                "content": f"Success from {provider.model_name}",
                "input_tokens": 50,
                "output_tokens": 100
            }
        
        services["fallback"]._call_provider_api = mock_unstable_api
        
        # Run continuous requests
        print("\nPhase 1: Continuous Request Processing")
        
        successes = 0
        failures = 0
        providers_used = []
        
        for i in range(30):
            request = LLMRequest(
                instance_id=prod_instance.id,
                prompt=f"Critical request #{i+1}: Validate deployment configuration",
                max_tokens=100,
                timeout=10.0
            )
            
            try:
                response = await services["fallback"].execute_request(
                    request,
                    prod_instance.llm_providers,
                    RoutingStrategy.ADAPTIVE  # Use adaptive routing for resilience
                )
                successes += 1
                providers_used.append(response.provider)
                
                if i % 5 == 0:
                    print(f"  Request {i+1}: ✓ {response.provider} ({response.model})")
                    
            except Exception as e:
                failures += 1
                print(f"  Request {i+1}: ✗ All providers failed - {e}")
        
        print(f"\nResults:")
        print(f"  Success rate: {successes/30*100:.1f}%")
        print(f"  Provider distribution: {dict((p, providers_used.count(p)) for p in set(providers_used))}")
        
        # Check circuit breaker status
        print("\nPhase 2: Circuit Breaker Status")
        
        for provider in [LLMProvider.OPENAI, LLMProvider.ANTHROPIC, LLMProvider.GEMINI]:
            is_open = services["fallback"]._is_circuit_open(provider)
            metrics = services["fallback"]._provider_metrics[provider]
            
            status = "OPEN" if is_open else "CLOSED"
            print(f"  {provider}: Circuit {status}, "
                  f"Consecutive failures: {metrics.consecutive_failures}")
        
        # Wait for circuit breakers to reset
        print("\nPhase 3: Recovery Period")
        print("  Waiting for circuit breakers to reset...")
        await asyncio.sleep(2)
        
        # Test recovery
        recovery_request = LLMRequest(
            instance_id=prod_instance.id,
            prompt="Post-recovery validation",
            max_tokens=100
        )
        
        # Reset failure patterns for recovery
        services["fallback"]._call_provider_api = AsyncMock(return_value={
            "content": "Recovery successful",
            "input_tokens": 50,
            "output_tokens": 50
        })
        
        response = await services["fallback"].execute_request(
            recovery_request,
            prod_instance.llm_providers
        )
        
        print(f"✓ Recovery successful with {response.provider}")
        
        # Final health report
        health = await services["fallback"].get_provider_health_report()
        print(f"\nFinal system health: {health['summary']['healthy_providers']}/{health['summary']['total_providers']} providers healthy")
        
        # Cleanup
        await services["lifecycle"].terminate_instance(prod_instance.id, "Test complete", force=True)
        await asyncio.sleep(1)
        await services["instance"].delete_instance(prod_instance.id)
    
    async def test_multi_tenant_load_balancing(self, services, test_persona_types, azure_devops_config, db):
        """Test load balancing across multiple tenants"""
        print("\n=== MULTI-TENANT LOAD BALANCING ===")
        
        # Create instances for different tenants
        tenants = ["TenantA", "TenantB", "TenantC"]
        tenant_instances = {}
        
        for tenant in tenants:
            instances = []
            
            # Each tenant gets 2 instances
            for i in range(2):
                instance = await services["instance"].create_instance(PersonaInstanceCreate(
                    instance_name=f"{tenant}-Worker-{i+1}-{uuid4().hex[:8]}",
                    persona_type_id=test_persona_types["developer"].id,
                    azure_devops_org=azure_devops_config["org_url"],
                    azure_devops_project=f"{tenant}Project",
                    llm_providers=[
                        LLMModel(provider=LLMProvider.OPENAI, model_name="gpt-3.5-turbo", api_key_env_var="OPENAI_API_KEY"),
                        LLMModel(provider=LLMProvider.ANTHROPIC, model_name="claude-instant", api_key_env_var="ANTHROPIC_API_KEY")
                    ],
                    spend_limit_daily=Decimal("50.00"),
                    spend_limit_monthly=Decimal("1000.00")
                ))
                instances.append(instance)
                await services["lifecycle"].provision_instance(instance.id)
            
            tenant_instances[tenant] = instances
        
        print(f"✓ Created {len(tenants)} tenants with {sum(len(v) for v in tenant_instances.values())} total instances")
        
        # Mock API with latency simulation
        provider_load = {"openai": 0, "anthropic": 0}
        
        async def mock_api_with_load(provider, request):
            # Simulate load
            provider_load[provider.provider] += 1
            
            # Add latency based on load
            base_latency = 0.5
            load_factor = provider_load[provider.provider] * 0.1
            total_latency = base_latency + load_factor
            
            await asyncio.sleep(total_latency)
            
            return {
                "content": f"Processed by {provider.model_name}",
                "input_tokens": 50,
                "output_tokens": 100
            }
        
        services["fallback"]._call_provider_api = mock_api_with_load
        
        # Simulate concurrent requests from all tenants
        print("\nSimulating concurrent load from all tenants:")
        
        async def tenant_workload(tenant_name, instances):
            results = []
            
            for i in range(10):  # 10 requests per tenant
                instance = instances[i % len(instances)]  # Round-robin between instances
                
                request = LLMRequest(
                    instance_id=instance.id,
                    prompt=f"{tenant_name} request {i+1}",
                    max_tokens=50
                )
                
                try:
                    response = await services["fallback"].execute_request(
                        request,
                        instance.llm_providers,
                        RoutingStrategy.ROUND_ROBIN  # Distribute load
                    )
                    results.append({
                        "tenant": tenant_name,
                        "provider": response.provider,
                        "latency": response.latency
                    })
                except Exception as e:
                    print(f"  {tenant_name} request {i+1} failed: {e}")
            
            return results
        
        # Run all tenant workloads concurrently
        workload_tasks = [
            tenant_workload(tenant, instances)
            for tenant, instances in tenant_instances.items()
        ]
        
        all_results = await asyncio.gather(*workload_tasks)
        
        # Analyze results
        print("\nLoad Distribution Analysis:")
        
        for tenant_idx, (tenant, results) in enumerate(zip(tenants, all_results)):
            provider_counts = {}
            total_latency = 0
            
            for result in results:
                provider = result["provider"]
                provider_counts[provider] = provider_counts.get(provider, 0) + 1
                total_latency += result["latency"]
            
            print(f"\n{tenant}:")
            print(f"  Requests processed: {len(results)}")
            print(f"  Provider distribution: {provider_counts}")
            print(f"  Average latency: {total_latency/len(results):.2f}s")
        
        print(f"\nGlobal provider load:")
        print(f"  OpenAI: {provider_load['openai']} requests")
        print(f"  Anthropic: {provider_load['anthropic']} requests")
        
        # Cleanup
        for instances in tenant_instances.values():
            for instance in instances:
                await services["instance"].delete_instance(instance.id)