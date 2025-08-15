"""
Unit tests for LLM Fallback Chain Service
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import random

from backend.services.llm_fallback_chain import (
    LLMFallbackChain,
    LLMRequest,
    LLMResponse,
    FailureReason,
    RoutingStrategy,
    ProviderMetrics
)
from backend.models.persona_instance import LLMModel, LLMProvider


class TestLLMFallbackChain:
    """Unit tests for LLMFallbackChain service"""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database manager"""
        db = AsyncMock()
        db.execute_query = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM provider service"""
        service = AsyncMock()
        service.initialize = AsyncMock()
        service.close = AsyncMock()
        service.validate_provider = AsyncMock(return_value=True)
        service.estimate_cost = AsyncMock(return_value={"total_cost": 0.01})
        service.MODEL_PRICING = {
            "gpt-4": {"input": 30.0, "output": 60.0},
            "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
            "claude-2": {"input": 8.0, "output": 24.0}
        }
        return service
    
    @pytest.fixture
    def mock_spend_service(self):
        """Create mock spend tracking service"""
        service = AsyncMock()
        service.initialize = AsyncMock()
        service.close = AsyncMock()
        service.record_llm_spend = AsyncMock()
        return service
    
    @pytest.fixture
    async def fallback_chain(self, mock_db, mock_llm_service, mock_spend_service):
        """Create fallback chain with mocked dependencies"""
        chain = LLMFallbackChain(mock_db)
        
        # Replace services with mocks
        chain.llm_service = mock_llm_service
        chain.spend_service = mock_spend_service
        
        # Mock database query for loading metrics
        mock_db.execute_query.return_value = []
        
        await chain.initialize()
        
        return chain
    
    @pytest.fixture
    def test_providers(self):
        """Create test LLM providers"""
        return [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            ),
            LLMModel(
                provider=LLMProvider.ANTHROPIC,
                model_name="claude-2",
                api_key_env_var="ANTHROPIC_API_KEY"
            ),
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                api_key_env_var="OPENAI_API_KEY"
            )
        ]
    
    @pytest.fixture
    def test_request(self):
        """Create test LLM request"""
        return LLMRequest(
            instance_id=uuid4(),
            prompt="Test prompt for fallback chain",
            max_tokens=100,
            temperature=0.7,
            system_message="You are a helpful assistant"
        )
    
    async def test_execute_request_success_first_provider(self, fallback_chain, test_request, test_providers):
        """Test successful request with first provider"""
        # Mock successful API call
        fallback_chain._call_provider_api = AsyncMock(return_value={
            "content": "Test response",
            "input_tokens": 10,
            "output_tokens": 20
        })
        
        response = await fallback_chain.execute_request(
            test_request,
            test_providers,
            RoutingStrategy.PRIORITY
        )
        
        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        assert response.provider == LLMProvider.OPENAI
        assert response.model == "gpt-4"
        assert response.fallback_used is False
        assert response.retry_count == 0
    
    async def test_execute_request_fallback_to_second_provider(self, fallback_chain, test_request, test_providers):
        """Test fallback to second provider when first fails"""
        # Mock first provider fails, second succeeds
        call_count = 0
        
        async def mock_call(provider, request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("API error: Rate limit exceeded")
            return {
                "content": "Fallback response",
                "input_tokens": 10,
                "output_tokens": 20
            }
        
        fallback_chain._call_provider_api = mock_call
        
        response = await fallback_chain.execute_request(
            test_request,
            test_providers,
            RoutingStrategy.PRIORITY
        )
        
        assert response.content == "Fallback response"
        assert response.provider == LLMProvider.ANTHROPIC
        assert response.model == "claude-2"
        assert response.fallback_used is True
    
    async def test_execute_request_all_providers_fail(self, fallback_chain, test_request, test_providers):
        """Test when all providers fail"""
        # Mock all providers fail
        fallback_chain._call_provider_api = AsyncMock(
            side_effect=Exception("API error")
        )
        
        with pytest.raises(Exception, match="All LLM providers failed"):
            await fallback_chain.execute_request(
                test_request,
                test_providers,
                RoutingStrategy.PRIORITY
            )
        
        # Verify all providers were tried
        assert fallback_chain._call_provider_api.call_count == len(test_providers)
    
    async def test_circuit_breaker_opens_after_failures(self, fallback_chain, test_request, test_providers):
        """Test circuit breaker opens after consecutive failures"""
        # Set threshold low for testing
        fallback_chain.circuit_breaker_threshold = 2
        
        # Mock API failures
        fallback_chain._call_provider_api = AsyncMock(
            side_effect=Exception("API error")
        )
        
        # First request - should try all providers
        try:
            await fallback_chain.execute_request(test_request, test_providers)
        except:
            pass
        
        # Second request with same provider - should trigger circuit breaker
        try:
            await fallback_chain.execute_request(test_request, [test_providers[0]])
        except:
            pass
        
        # Check circuit breaker is open
        assert fallback_chain._is_circuit_open(LLMProvider.OPENAI)
        
        # Third request should skip provider with open circuit
        available = await fallback_chain._filter_available_providers(
            [test_providers[0]], None
        )
        assert len(available) == 0
    
    async def test_rate_limiting_handling(self, fallback_chain, test_request, test_providers):
        """Test rate limit handling"""
        # Mock rate limit error
        fallback_chain._call_provider_api = AsyncMock(
            side_effect=Exception("Rate limit exceeded")
        )
        
        # First request fails with rate limit
        try:
            await fallback_chain.execute_request(test_request, [test_providers[0]])
        except:
            pass
        
        # Provider should be rate limited
        assert fallback_chain._is_rate_limited(LLMProvider.OPENAI)
        
        # Should filter out rate limited provider
        available = await fallback_chain._filter_available_providers(
            test_providers, None
        )
        assert all(p.provider != LLMProvider.OPENAI for p in available)
    
    async def test_caching_successful_responses(self, fallback_chain, test_request, test_providers):
        """Test response caching"""
        # Mock successful API call
        fallback_chain._call_provider_api = AsyncMock(return_value={
            "content": "Cached response",
            "input_tokens": 10,
            "output_tokens": 20
        })
        
        # First request
        response1 = await fallback_chain.execute_request(
            test_request,
            test_providers
        )
        
        # Second identical request should use cache
        response2 = await fallback_chain.execute_request(
            test_request,
            test_providers
        )
        
        # Should only call API once
        assert fallback_chain._call_provider_api.call_count == 1
        assert response1.content == response2.content
    
    async def test_routing_strategy_least_cost(self, fallback_chain, test_request, test_providers):
        """Test least cost routing strategy"""
        ordered = await fallback_chain._order_providers(
            test_providers,
            RoutingStrategy.LEAST_COST,
            test_request
        )
        
        # Should order by cost: gpt-3.5-turbo < claude-2 < gpt-4
        assert ordered[0].model_name == "gpt-3.5-turbo"
        assert ordered[-1].model_name == "gpt-4"
    
    async def test_routing_strategy_adaptive(self, fallback_chain, test_request, test_providers):
        """Test adaptive routing strategy"""
        # Set up metrics for providers
        metrics_gpt4 = fallback_chain._provider_metrics[LLMProvider.OPENAI]
        metrics_gpt4.success_count = 100
        metrics_gpt4.failure_count = 5
        metrics_gpt4.total_latency = 200.0  # 2s average
        metrics_gpt4.last_success = datetime.utcnow()
        
        metrics_claude = fallback_chain._provider_metrics[LLMProvider.ANTHROPIC]
        metrics_claude.success_count = 50
        metrics_claude.failure_count = 50  # Lower success rate
        metrics_claude.total_latency = 50.0  # 1s average
        
        ordered = await fallback_chain._order_providers(
            test_providers[:2],  # Just GPT-4 and Claude
            RoutingStrategy.ADAPTIVE,
            test_request
        )
        
        # GPT-4 should be preferred due to higher success rate
        assert ordered[0].provider == LLMProvider.OPENAI
    
    async def test_failure_classification(self, fallback_chain):
        """Test failure reason classification"""
        test_cases = [
            ("Rate limit exceeded", FailureReason.RATE_LIMIT),
            ("Too many requests", FailureReason.RATE_LIMIT),
            ("Request timeout", FailureReason.TIMEOUT),
            ("Invalid API key", FailureReason.AUTHENTICATION),
            ("Unauthorized", FailureReason.AUTHENTICATION),
            ("Network error", FailureReason.NETWORK_ERROR),
            ("Service unavailable", FailureReason.SERVICE_UNAVAILABLE),
            ("503 Service Unavailable", FailureReason.SERVICE_UNAVAILABLE),
            ("Invalid response format", FailureReason.INVALID_RESPONSE),
            ("Unknown error", FailureReason.API_ERROR)
        ]
        
        for error_msg, expected_reason in test_cases:
            reason = fallback_chain._classify_failure(Exception(error_msg))
            assert reason == expected_reason
    
    async def test_provider_health_tracking(self, fallback_chain):
        """Test provider health tracking"""
        metrics = ProviderMetrics()
        
        # Healthy provider
        metrics.success_count = 100
        metrics.failure_count = 2
        metrics.consecutive_failures = 0
        assert metrics.is_healthy
        
        # Too many consecutive failures
        metrics.consecutive_failures = 3
        assert not metrics.is_healthy
        
        # Recent failure with no success since
        metrics.consecutive_failures = 1
        metrics.last_failure = datetime.utcnow()
        metrics.last_success = datetime.utcnow() - timedelta(minutes=10)
        assert not metrics.is_healthy
    
    async def test_excluded_providers(self, fallback_chain, test_request, test_providers):
        """Test excluding specific providers"""
        test_request.excluded_providers = {LLMProvider.OPENAI}
        
        available = await fallback_chain._filter_available_providers(
            test_providers,
            test_request.excluded_providers
        )
        
        # Should exclude all OpenAI providers
        assert all(p.provider != LLMProvider.OPENAI for p in available)
        assert len(available) == 1  # Only Anthropic
    
    async def test_preferred_providers(self, fallback_chain, test_request, test_providers):
        """Test preferred provider ordering"""
        test_request.preferred_providers = [LLMProvider.ANTHROPIC]
        
        ordered = await fallback_chain._order_providers(
            test_providers,
            RoutingStrategy.PRIORITY,
            test_request
        )
        
        # Anthropic should be first
        assert ordered[0].provider == LLMProvider.ANTHROPIC
    
    async def test_get_provider_health_report(self, fallback_chain):
        """Test getting provider health report"""
        # Set up some metrics
        metrics = fallback_chain._provider_metrics[LLMProvider.OPENAI]
        metrics.success_count = 100
        metrics.failure_count = 10
        metrics.consecutive_failures = 1
        
        # Add circuit breaker
        fallback_chain._circuit_breakers[LLMProvider.ANTHROPIC] = datetime.utcnow()
        
        report = await fallback_chain.get_provider_health_report()
        
        assert "providers" in report
        assert "summary" in report
        assert report["summary"]["circuit_breakers_open"] == 1
        
        openai_report = report["providers"].get("openai")
        assert openai_report is not None
        assert openai_report["success_rate"] == pytest.approx(0.909, rel=0.01)
        assert openai_report["total_requests"] == 110
    
    async def test_reset_provider_metrics(self, fallback_chain):
        """Test resetting provider metrics"""
        # Set up metrics
        fallback_chain._provider_metrics[LLMProvider.OPENAI].success_count = 100
        fallback_chain._circuit_breakers[LLMProvider.OPENAI] = datetime.utcnow()
        fallback_chain._rate_limits[LLMProvider.OPENAI] = datetime.utcnow()
        
        # Reset specific provider
        await fallback_chain.reset_provider_metrics(LLMProvider.OPENAI)
        
        assert fallback_chain._provider_metrics[LLMProvider.OPENAI].success_count == 0
        assert LLMProvider.OPENAI not in fallback_chain._circuit_breakers
        assert LLMProvider.OPENAI not in fallback_chain._rate_limits
        
        # Reset all
        fallback_chain._provider_metrics[LLMProvider.ANTHROPIC].success_count = 50
        await fallback_chain.reset_provider_metrics()
        
        assert len(fallback_chain._provider_metrics) == 0
    
    async def test_prepare_request_openai_format(self, fallback_chain, test_request):
        """Test request preparation for OpenAI"""
        provider = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4",
            api_key_env_var="OPENAI_API_KEY"
        )
        
        prepared = await fallback_chain._prepare_request(test_request, provider)
        
        assert prepared["model"] == "gpt-4"
        assert len(prepared["messages"]) == 2
        assert prepared["messages"][0]["role"] == "system"
        assert prepared["messages"][1]["role"] == "user"
        assert prepared["max_tokens"] == 100
        assert prepared["temperature"] == 0.7
    
    async def test_prepare_request_anthropic_format(self, fallback_chain, test_request):
        """Test request preparation for Anthropic"""
        provider = LLMModel(
            provider=LLMProvider.ANTHROPIC,
            model_name="claude-2",
            api_key_env_var="ANTHROPIC_API_KEY"
        )
        
        prepared = await fallback_chain._prepare_request(test_request, provider)
        
        assert prepared["model"] == "claude-2"
        assert prepared["system"] == test_request.system_message
        assert len(prepared["messages"]) == 1
        assert prepared["messages"][0]["role"] == "user"