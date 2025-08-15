"""
Integration tests for LLM Fallback Chain Service
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from decimal import Decimal

from backend.services.llm_fallback_chain import (
    LLMFallbackChain,
    LLMRequest,
    RoutingStrategy,
    FailureReason
)
from backend.models.persona_instance import (
    PersonaInstanceCreate,
    LLMProvider,
    LLMModel
)
from backend.services.persona_instance_service import PersonaInstanceService
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.asyncio
class TestLLMFallbackChainIntegration:
    """Integration tests with real database"""
    
    @pytest.fixture
    async def fallback_chain(self, db):
        """Create fallback chain with real database"""
        chain = LLMFallbackChain(db)
        await chain.initialize()
        yield chain
        await chain.close()
    
    @pytest.fixture
    async def test_persona_type(self, db):
        """Create test persona type"""
        repo = PersonaTypeRepository(db)
        
        persona_type = await repo.create(PersonaTypeCreate(
            type_name=f"fallback-test-{uuid4().hex[:8]}",
            display_name="Fallback Test Developer",
            category=PersonaCategory.DEVELOPMENT,
            description="Test persona for fallback chain",
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
        """Create test instance with multiple LLM providers"""
        service = PersonaInstanceService(db)
        
        instance = await service.create_instance(PersonaInstanceCreate(
            instance_name=f"FallbackTest-{uuid4().hex[:8]}",
            persona_type_id=test_persona_type.id,
            azure_devops_org=azure_devops_config["org_url"],
            azure_devops_project="FallbackTestProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY",
                    temperature=0.7
                ),
                LLMModel(
                    provider=LLMProvider.ANTHROPIC,
                    model_name="claude-2",
                    api_key_env_var="ANTHROPIC_API_KEY",
                    temperature=0.7
                ),
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY",
                    temperature=0.7
                )
            ],
            spend_limit_daily=Decimal("100.00"),
            spend_limit_monthly=Decimal("2000.00")
        ))
        
        yield instance
        
        # Cleanup
        await db.execute_query(
            "DELETE FROM orchestrator.persona_instances WHERE id = $1",
            instance.id
        )
    
    async def test_fallback_chain_with_real_providers(self, fallback_chain, test_instance):
        """Test fallback chain with real provider configuration"""
        request = LLMRequest(
            instance_id=test_instance.id,
            prompt="Explain the concept of dependency injection",
            max_tokens=150,
            temperature=0.7,
            system_message="You are a software engineering expert"
        )
        
        # Note: This will fail with actual API calls unless keys are configured
        # For integration testing, we mock the API calls
        async def mock_api_call(provider, request):
            # Simulate different responses from providers
            if provider.model_name == "gpt-4":
                return {
                    "content": "GPT-4: Dependency injection is a design pattern...",
                    "input_tokens": 20,
                    "output_tokens": 100
                }
            elif provider.model_name == "claude-2":
                return {
                    "content": "Claude: Dependency injection is a technique...",
                    "input_tokens": 20,
                    "output_tokens": 90
                }
            else:
                return {
                    "content": "GPT-3.5: DI is a pattern where dependencies...",
                    "input_tokens": 20,
                    "output_tokens": 80
                }
        
        fallback_chain._call_provider_api = mock_api_call
        
        # Execute request with priority routing
        response = await fallback_chain.execute_request(
            request,
            test_instance.llm_providers,
            RoutingStrategy.PRIORITY
        )
        
        assert response.content.startswith("GPT-4:")
        assert response.provider == LLMProvider.OPENAI
        assert response.model == "gpt-4"
        
        # Verify spend was recorded
        query = """
        SELECT COUNT(*) as count 
        FROM orchestrator.spend_tracking 
        WHERE instance_id = $1
        """
        result = await fallback_chain.db.execute_query(
            query, test_instance.id, fetch_one=True
        )
        assert result['count'] > 0
    
    async def test_fallback_on_provider_failure(self, fallback_chain, test_instance):
        """Test fallback when primary provider fails"""
        request = LLMRequest(
            instance_id=test_instance.id,
            prompt="Test fallback scenario",
            max_tokens=100
        )
        
        # Mock API calls with first provider failing
        call_count = 0
        async def mock_api_with_failure(provider, req):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # First provider fails
                raise Exception("Rate limit exceeded")
            else:
                # Fallback provider succeeds
                return {
                    "content": f"Response from {provider.model_name}",
                    "input_tokens": 10,
                    "output_tokens": 20
                }
        
        fallback_chain._call_provider_api = mock_api_with_failure
        
        response = await fallback_chain.execute_request(
            request,
            test_instance.llm_providers
        )
        
        # Should have fallen back to second provider
        assert response.provider == LLMProvider.ANTHROPIC
        assert response.model == "claude-2"
        assert response.fallback_used is True
        
        # Check failure was recorded
        metrics = fallback_chain._provider_metrics[LLMProvider.OPENAI]
        assert metrics.failure_count > 0
        assert FailureReason.RATE_LIMIT in metrics.failure_reasons
    
    async def test_cost_based_routing(self, fallback_chain, test_instance):
        """Test least cost routing strategy"""
        request = LLMRequest(
            instance_id=test_instance.id,
            prompt="Cost optimization test",
            max_tokens=100
        )
        
        # Mock successful API calls
        async def mock_api(provider, req):
            return {
                "content": f"Response from {provider.model_name}",
                "input_tokens": 10,
                "output_tokens": 20
            }
        
        fallback_chain._call_provider_api = mock_api
        
        # Execute with least cost routing
        response = await fallback_chain.execute_request(
            request,
            test_instance.llm_providers,
            RoutingStrategy.LEAST_COST
        )
        
        # Should select cheapest model (gpt-3.5-turbo)
        assert response.model == "gpt-3.5-turbo"
        assert response.cost < 0.01  # Very cheap
    
    async def test_circuit_breaker_persistence(self, fallback_chain, test_instance):
        """Test circuit breaker behavior persists across requests"""
        request = LLMRequest(
            instance_id=test_instance.id,
            prompt="Circuit breaker test",
            max_tokens=50
        )
        
        # Lower threshold for testing
        fallback_chain.circuit_breaker_threshold = 2
        
        # Mock consistent failures for one provider
        async def mock_failing_api(provider, req):
            if provider.provider == LLMProvider.OPENAI:
                raise Exception("Service unavailable")
            return {
                "content": "Success",
                "input_tokens": 10,
                "output_tokens": 10
            }
        
        fallback_chain._call_provider_api = mock_failing_api
        
        # Make multiple requests to trigger circuit breaker
        for i in range(3):
            try:
                response = await fallback_chain.execute_request(
                    request,
                    test_instance.llm_providers
                )
                # Should succeed with Anthropic
                assert response.provider == LLMProvider.ANTHROPIC
            except:
                pass  # Some requests might fail entirely
        
        # Circuit breaker should be open for OpenAI
        assert fallback_chain._is_circuit_open(LLMProvider.OPENAI)
        
        # Future requests should skip OpenAI entirely
        available = await fallback_chain._filter_available_providers(
            test_instance.llm_providers,
            None
        )
        openai_providers = [p for p in available if p.provider == LLMProvider.OPENAI]
        assert len(openai_providers) == 0
    
    async def test_adaptive_routing_with_metrics(self, fallback_chain, test_instance, db):
        """Test adaptive routing based on performance metrics"""
        # Simulate historical performance data
        # GPT-4: High success rate but slow and expensive
        # Claude-2: Medium success rate, medium speed
        # GPT-3.5: Lower success rate but fast and cheap
        
        # Insert mock historical data
        for i in range(100):
            # GPT-4: 95% success, slow
            await db.execute_query("""
                INSERT INTO orchestrator.llm_usage_logs 
                (id, instance_id, provider, model_name, input_tokens, output_tokens,
                 total_tokens, cost, latency, success, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """, 
                uuid4(), str(test_instance.id), "openai", "gpt-4",
                100, 200, 300, 0.018, 2.5 if i % 20 != 0 else 0.5,  # Usually slow
                i % 20 != 0,  # 95% success
                datetime.utcnow() - timedelta(hours=i)
            )
            
            # Claude-2: 80% success, medium speed
            if i % 5 != 0:  # 80% of the time
                await db.execute_query("""
                    INSERT INTO orchestrator.llm_usage_logs 
                    (id, instance_id, provider, model_name, input_tokens, output_tokens,
                     total_tokens, cost, latency, success, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                    uuid4(), str(test_instance.id), "anthropic", "claude-2",
                    100, 200, 300, 0.008, 1.5,
                    True,
                    datetime.utcnow() - timedelta(hours=i)
                )
        
        # Reload metrics
        await fallback_chain._load_provider_metrics()
        
        request = LLMRequest(
            instance_id=test_instance.id,
            prompt="Adaptive routing test",
            max_tokens=100
        )
        
        # Mock successful API
        async def mock_api(provider, req):
            return {
                "content": f"Response from {provider.model_name}",
                "input_tokens": 10,
                "output_tokens": 20
            }
        
        fallback_chain._call_provider_api = mock_api
        
        # Use adaptive routing
        response = await fallback_chain.execute_request(
            request,
            test_instance.llm_providers,
            RoutingStrategy.ADAPTIVE
        )
        
        # Should prefer GPT-4 due to high success rate despite cost
        assert response.provider == LLMProvider.OPENAI
        assert response.model == "gpt-4"
    
    async def test_provider_health_monitoring(self, fallback_chain, test_instance):
        """Test provider health monitoring and reporting"""
        # Simulate various health conditions
        request = LLMRequest(
            instance_id=test_instance.id,
            prompt="Health monitoring test",
            max_tokens=50
        )
        
        # Create mixed success/failure pattern
        results = [True, True, False, True, False, False, True]  # Some failures
        
        for i, should_succeed in enumerate(results):
            async def mock_api(provider, req):
                if not should_succeed and provider.provider == LLMProvider.OPENAI:
                    raise Exception("Temporary failure")
                return {
                    "content": "Success",
                    "input_tokens": 10,
                    "output_tokens": 10
                }
            
            fallback_chain._call_provider_api = mock_api
            
            try:
                await fallback_chain.execute_request(
                    request,
                    [test_instance.llm_providers[0]]  # Just OpenAI GPT-4
                )
            except:
                pass  # Expected for failures
        
        # Get health report
        report = await fallback_chain.get_provider_health_report()
        
        assert "providers" in report
        assert "openai" in report["providers"]
        
        openai_health = report["providers"]["openai"]
        assert openai_health["total_requests"] == len(results)
        assert openai_health["success_rate"] < 1.0  # Had some failures
        assert openai_health["success_rate"] > 0.0  # Had some successes
    
    async def test_spend_limit_enforcement(self, fallback_chain, test_instance, db):
        """Test that fallback chain respects spend limits"""
        # Set very low spend limit
        await db.execute_query("""
            UPDATE orchestrator.persona_instances
            SET spend_limit_daily = $1,
                current_spend_daily = $2
            WHERE id = $3
        """, Decimal("1.00"), Decimal("0.99"), test_instance.id)
        
        request = LLMRequest(
            instance_id=test_instance.id,
            prompt="Spend limit test",
            max_tokens=1000  # High token count
        )
        
        # Mock expensive API call
        async def mock_expensive_api(provider, req):
            return {
                "content": "Expensive response",
                "input_tokens": 500,
                "output_tokens": 500
            }
        
        fallback_chain._call_provider_api = mock_expensive_api
        
        # Should succeed but trigger spend tracking
        response = await fallback_chain.execute_request(
            request,
            test_instance.llm_providers
        )
        
        # Check if spend was recorded
        spend_result = await db.execute_query("""
            SELECT current_spend_daily
            FROM orchestrator.persona_instances
            WHERE id = $1
        """, test_instance.id, fetch_one=True)
        
        # Should have increased spend
        assert float(spend_result['current_spend_daily']) > 0.99