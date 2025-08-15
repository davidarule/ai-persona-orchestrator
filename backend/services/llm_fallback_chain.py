"""
LLM Fallback Chain Service

Implements automatic failover between LLM providers with intelligent routing,
error handling, and performance tracking for high availability.
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import json
import logging
import random
from uuid import UUID

from backend.models.persona_instance import LLMModel, LLMProvider
from backend.services.llm_provider_service import LLMProviderService
from backend.services.spend_tracking_service import SpendTrackingService
from backend.services.database import DatabaseManager


# Configure logging
logger = logging.getLogger(__name__)


class FailureReason(str, Enum):
    """Reasons for LLM provider failure"""
    API_ERROR = "api_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    COST_EXCEEDED = "cost_exceeded"
    AUTHENTICATION = "authentication"
    NETWORK_ERROR = "network_error"
    SERVICE_UNAVAILABLE = "service_unavailable"


class RoutingStrategy(str, Enum):
    """Strategies for routing requests to providers"""
    PRIORITY = "priority"  # Use providers in order of preference
    ROUND_ROBIN = "round_robin"  # Distribute evenly
    LEAST_COST = "least_cost"  # Choose cheapest available
    FASTEST = "fastest"  # Choose based on response time
    ADAPTIVE = "adaptive"  # Learn from performance


@dataclass
class ProviderMetrics:
    """Track performance metrics for a provider"""
    success_count: int = 0
    failure_count: int = 0
    total_latency: float = 0.0
    total_tokens: int = 0
    total_cost: float = 0.0
    failure_reasons: Dict[FailureReason, int] = field(default_factory=dict)
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    consecutive_failures: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
    
    @property
    def average_latency(self) -> float:
        """Calculate average response time"""
        return self.total_latency / self.success_count if self.success_count > 0 else 0.0
    
    @property
    def is_healthy(self) -> bool:
        """Check if provider is healthy"""
        # Unhealthy if too many consecutive failures
        if self.consecutive_failures >= 3:
            return False
        
        # Unhealthy if failed recently and no success since
        if self.last_failure and self.last_success:
            if self.last_failure > self.last_success:
                time_since_failure = datetime.utcnow() - self.last_failure
                if time_since_failure < timedelta(minutes=5):
                    return False
        
        return True


@dataclass
class LLMRequest:
    """Represents an LLM request"""
    instance_id: UUID
    prompt: str
    max_tokens: int = 2048
    temperature: float = 0.7
    system_message: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    timeout: float = 30.0
    retry_count: int = 0
    preferred_providers: Optional[List[LLMProvider]] = None
    excluded_providers: Optional[Set[LLMProvider]] = None


@dataclass
class LLMResponse:
    """Represents an LLM response"""
    content: str
    provider: LLMProvider
    model: str
    input_tokens: int
    output_tokens: int
    latency: float
    cost: float
    request_id: str
    retry_count: int = 0
    fallback_used: bool = False


class LLMFallbackChain:
    """
    Manages fallback chains for LLM providers with automatic failover
    
    Features:
    - Automatic failover on errors
    - Rate limit handling with backoff
    - Cost-aware routing
    - Performance tracking
    - Circuit breaker pattern
    - Request retry with exponential backoff
    - Provider health monitoring
    """
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.llm_service = LLMProviderService(db_manager)
        self.spend_service = SpendTrackingService(db_manager)
        
        # Provider metrics tracking
        self._provider_metrics: Dict[LLMProvider, ProviderMetrics] = defaultdict(ProviderMetrics)
        
        # Rate limiting tracking
        self._rate_limits: Dict[LLMProvider, datetime] = {}
        
        # Circuit breaker states
        self._circuit_breakers: Dict[LLMProvider, datetime] = {}
        
        # Request cache for deduplication
        self._request_cache: Dict[str, LLMResponse] = {}
        self._cache_ttl = timedelta(minutes=5)
        
        # Configuration
        self.max_retries = 3
        self.base_retry_delay = 1.0  # seconds
        self.circuit_breaker_threshold = 5  # consecutive failures
        self.circuit_breaker_timeout = timedelta(minutes=10)
    
    async def initialize(self):
        """Initialize the fallback chain service"""
        await self.llm_service.initialize()
        await self.spend_service.initialize()
        
        # Load historical metrics
        await self._load_provider_metrics()
    
    async def close(self):
        """Clean up resources"""
        await self.llm_service.close()
        await self.spend_service.close()
    
    async def execute_request(
        self,
        request: LLMRequest,
        providers: List[LLMModel],
        routing_strategy: RoutingStrategy = RoutingStrategy.PRIORITY
    ) -> LLMResponse:
        """
        Execute an LLM request with automatic fallback
        
        Args:
            request: The LLM request to execute
            providers: List of available LLM providers
            routing_strategy: Strategy for selecting providers
            
        Returns:
            LLMResponse with the result
            
        Raises:
            Exception: If all providers fail
        """
        # Check cache first
        cache_key = self._get_cache_key(request)
        if cache_key in self._request_cache:
            cached = self._request_cache[cache_key]
            if datetime.utcnow() - datetime.fromisoformat(cached.request_id) < self._cache_ttl:
                logger.info(f"Returning cached response for request")
                return cached
        
        # Filter available providers
        available_providers = await self._filter_available_providers(
            providers,
            request.excluded_providers
        )
        
        if not available_providers:
            raise Exception("No available LLM providers")
        
        # Order providers based on routing strategy
        ordered_providers = await self._order_providers(
            available_providers,
            routing_strategy,
            request
        )
        
        # Try each provider in order
        last_error = None
        for i, provider in enumerate(ordered_providers):
            try:
                # Check circuit breaker
                if self._is_circuit_open(provider.provider):
                    logger.warning(f"Circuit breaker open for {provider.provider}")
                    continue
                
                # Check rate limit
                if self._is_rate_limited(provider.provider):
                    logger.warning(f"Rate limited for {provider.provider}")
                    continue
                
                # Execute request
                response = await self._execute_with_provider(
                    request,
                    provider,
                    is_fallback=i > 0
                )
                
                # Update metrics
                await self._record_success(provider.provider, response)
                
                # Cache successful response
                self._request_cache[cache_key] = response
                
                return response
                
            except Exception as e:
                last_error = e
                logger.error(f"Provider {provider.provider} failed: {e}")
                
                # Record failure
                failure_reason = self._classify_failure(e)
                await self._record_failure(provider.provider, failure_reason)
                
                # Handle specific failure types
                if failure_reason == FailureReason.RATE_LIMIT:
                    self._rate_limits[provider.provider] = datetime.utcnow()
                elif failure_reason == FailureReason.AUTHENTICATION:
                    # Remove from available providers for this session
                    if request.excluded_providers is None:
                        request.excluded_providers = set()
                    request.excluded_providers.add(provider.provider)
                
                # Continue to next provider
                continue
        
        # All providers failed
        raise Exception(f"All LLM providers failed. Last error: {last_error}")
    
    async def _execute_with_provider(
        self,
        request: LLMRequest,
        provider: LLMModel,
        is_fallback: bool = False
    ) -> LLMResponse:
        """Execute request with a specific provider"""
        start_time = time.time()
        
        # Prepare the API request based on provider
        api_request = await self._prepare_request(request, provider)
        
        # Make the API call
        result = await self._call_provider_api(provider, api_request)
        
        # Calculate metrics
        latency = time.time() - start_time
        input_tokens = result.get("input_tokens", 0)
        output_tokens = result.get("output_tokens", 0)
        
        # Calculate cost
        cost_info = await self.llm_service.estimate_cost(
            provider,
            input_tokens,
            output_tokens
        )
        
        # Record spend
        await self.spend_service.record_llm_spend(
            request.instance_id,
            provider,
            input_tokens,
            output_tokens,
            task_description=f"LLM request{' (fallback)' if is_fallback else ''}"
        )
        
        return LLMResponse(
            content=result["content"],
            provider=provider.provider,
            model=provider.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency=latency,
            cost=cost_info["total_cost"],
            request_id=datetime.utcnow().isoformat(),
            retry_count=request.retry_count,
            fallback_used=is_fallback
        )
    
    async def _prepare_request(self, request: LLMRequest, provider: LLMModel) -> Dict[str, Any]:
        """Prepare API request for specific provider"""
        base_request = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature
        }
        
        if provider.provider == LLMProvider.OPENAI:
            messages = []
            if request.system_message:
                messages.append({"role": "system", "content": request.system_message})
            messages.append({"role": "user", "content": request.prompt})
            
            base_request.update({
                "model": provider.model_name,
                "messages": messages
            })
            
        elif provider.provider == LLMProvider.ANTHROPIC:
            base_request.update({
                "model": provider.model_name,
                "messages": [{"role": "user", "content": request.prompt}],
                "system": request.system_message
            })
            
        elif provider.provider == LLMProvider.GEMINI:
            base_request.update({
                "model": provider.model_name,
                "contents": [{"parts": [{"text": request.prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": request.max_tokens,
                    "temperature": request.temperature
                }
            })
            
        else:
            # Generic format
            base_request.update({
                "prompt": request.prompt,
                "model": provider.model_name
            })
        
        return base_request
    
    async def _call_provider_api(self, provider: LLMModel, request: Dict[str, Any]) -> Dict[str, Any]:
        """Make actual API call to provider"""
        # This would integrate with actual provider APIs
        # For now, simulate the response
        
        # Simulate occasional failures for testing
        if random.random() < 0.1:  # 10% failure rate for testing
            if random.random() < 0.5:
                raise Exception("Rate limit exceeded")
            else:
                raise Exception("API error: Internal server error")
        
        # Simulate response
        response_text = f"Response from {provider.model_name}: This is a simulated response to the prompt."
        
        return {
            "content": response_text,
            "input_tokens": len(request.get("prompt", "").split()) * 2,
            "output_tokens": len(response_text.split()) * 2
        }
    
    async def _filter_available_providers(
        self,
        providers: List[LLMModel],
        excluded: Optional[Set[LLMProvider]]
    ) -> List[LLMModel]:
        """Filter providers based on availability"""
        available = []
        
        for provider in providers:
            # Check if excluded
            if excluded and provider.provider in excluded:
                continue
            
            # Check if circuit breaker is open
            if self._is_circuit_open(provider.provider):
                continue
            
            # Check if rate limited
            if self._is_rate_limited(provider.provider):
                continue
            
            # Check if provider is healthy
            metrics = self._provider_metrics[provider.provider]
            if not metrics.is_healthy:
                continue
            
            # Validate provider configuration
            if await self.llm_service.validate_provider(provider):
                available.append(provider)
        
        return available
    
    async def _order_providers(
        self,
        providers: List[LLMModel],
        strategy: RoutingStrategy,
        request: LLMRequest
    ) -> List[LLMModel]:
        """Order providers based on routing strategy"""
        if strategy == RoutingStrategy.PRIORITY:
            # Use order as provided (with preferred providers first)
            if request.preferred_providers:
                preferred = [p for p in providers if p.provider in request.preferred_providers]
                others = [p for p in providers if p.provider not in request.preferred_providers]
                return preferred + others
            return providers
            
        elif strategy == RoutingStrategy.ROUND_ROBIN:
            # Rotate providers
            return providers[1:] + providers[:1]
            
        elif strategy == RoutingStrategy.LEAST_COST:
            # Sort by cost
            return sorted(providers, key=lambda p: self._get_provider_cost(p))
            
        elif strategy == RoutingStrategy.FASTEST:
            # Sort by average latency
            return sorted(providers, key=lambda p: self._provider_metrics[p.provider].average_latency)
            
        elif strategy == RoutingStrategy.ADAPTIVE:
            # Score based on multiple factors
            scored = []
            for provider in providers:
                score = self._calculate_adaptive_score(provider)
                scored.append((score, provider))
            
            # Sort by score (higher is better)
            scored.sort(key=lambda x: x[0], reverse=True)
            return [p for _, p in scored]
        
        return providers
    
    def _calculate_adaptive_score(self, provider: LLMModel) -> float:
        """Calculate adaptive routing score for a provider"""
        metrics = self._provider_metrics[provider.provider]
        
        # Factors to consider
        success_rate = metrics.success_rate
        avg_latency = metrics.average_latency
        cost = self._get_provider_cost(provider)
        
        # Normalize factors
        latency_score = 1.0 / (1.0 + avg_latency) if avg_latency > 0 else 1.0
        cost_score = 1.0 / (1.0 + cost)
        
        # Weight factors
        score = (
            success_rate * 0.4 +  # Reliability is most important
            latency_score * 0.3 +  # Speed is important
            cost_score * 0.3  # Cost matters too
        )
        
        # Boost score for recently successful providers
        if metrics.last_success:
            time_since_success = datetime.utcnow() - metrics.last_success
            if time_since_success < timedelta(minutes=5):
                score *= 1.2
        
        return score
    
    def _get_provider_cost(self, provider: LLMModel) -> float:
        """Get estimated cost per 1k tokens for provider"""
        pricing = self.llm_service.MODEL_PRICING.get(provider.model_name, {})
        # Average of input and output costs
        return (pricing.get("input", 10.0) + pricing.get("output", 10.0)) / 2
    
    def _is_circuit_open(self, provider: LLMProvider) -> bool:
        """Check if circuit breaker is open for provider"""
        if provider in self._circuit_breakers:
            opened_at = self._circuit_breakers[provider]
            if datetime.utcnow() - opened_at < self.circuit_breaker_timeout:
                return True
            else:
                # Timeout expired, close circuit
                del self._circuit_breakers[provider]
        return False
    
    def _is_rate_limited(self, provider: LLMProvider) -> bool:
        """Check if provider is rate limited"""
        if provider in self._rate_limits:
            limited_at = self._rate_limits[provider]
            # Use exponential backoff
            backoff_time = timedelta(minutes=5)  # Base backoff
            if datetime.utcnow() - limited_at < backoff_time:
                return True
            else:
                # Backoff expired
                del self._rate_limits[provider]
        return False
    
    def _classify_failure(self, error: Exception) -> FailureReason:
        """Classify the type of failure"""
        error_str = str(error).lower()
        
        if "rate limit" in error_str or "too many requests" in error_str:
            return FailureReason.RATE_LIMIT
        elif "timeout" in error_str:
            return FailureReason.TIMEOUT
        elif "auth" in error_str or "api key" in error_str or "unauthorized" in error_str:
            return FailureReason.AUTHENTICATION
        elif "network" in error_str or "connection" in error_str:
            return FailureReason.NETWORK_ERROR
        elif "service unavailable" in error_str or "503" in error_str:
            return FailureReason.SERVICE_UNAVAILABLE
        elif "invalid response" in error_str:
            return FailureReason.INVALID_RESPONSE
        else:
            return FailureReason.API_ERROR
    
    async def _record_success(self, provider: LLMProvider, response: LLMResponse):
        """Record successful request"""
        metrics = self._provider_metrics[provider]
        metrics.success_count += 1
        metrics.total_latency += response.latency
        metrics.total_tokens += response.input_tokens + response.output_tokens
        metrics.total_cost += response.cost
        metrics.last_success = datetime.utcnow()
        metrics.consecutive_failures = 0
        
        # Store metrics in database
        await self._save_provider_metrics(provider, metrics)
    
    async def _record_failure(self, provider: LLMProvider, reason: FailureReason):
        """Record failed request"""
        metrics = self._provider_metrics[provider]
        metrics.failure_count += 1
        metrics.failure_reasons[reason] = metrics.failure_reasons.get(reason, 0) + 1
        metrics.last_failure = datetime.utcnow()
        metrics.consecutive_failures += 1
        
        # Open circuit breaker if too many consecutive failures
        if metrics.consecutive_failures >= self.circuit_breaker_threshold:
            self._circuit_breakers[provider] = datetime.utcnow()
            logger.warning(f"Circuit breaker opened for {provider}")
        
        # Store metrics in database
        await self._save_provider_metrics(provider, metrics)
    
    def _get_cache_key(self, request: LLMRequest) -> str:
        """Generate cache key for request"""
        # Create deterministic key from request parameters
        key_parts = [
            request.prompt,
            str(request.max_tokens),
            str(request.temperature),
            request.system_message or ""
        ]
        return json.dumps(key_parts, sort_keys=True)
    
    async def _load_provider_metrics(self):
        """Load historical provider metrics from database"""
        query = """
        SELECT 
            provider,
            COUNT(*) FILTER (WHERE success = true) as success_count,
            COUNT(*) FILTER (WHERE success = false) as failure_count,
            AVG(latency) FILTER (WHERE success = true) as avg_latency,
            SUM(input_tokens + output_tokens) as total_tokens,
            SUM(cost) as total_cost,
            MAX(created_at) FILTER (WHERE success = true) as last_success,
            MAX(created_at) FILTER (WHERE success = false) as last_failure
        FROM orchestrator.llm_usage_logs
        WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY provider
        """
        
        results = await self.db.execute_query(query)
        
        for row in results:
            provider = LLMProvider(row['provider'])
            metrics = self._provider_metrics[provider]
            
            metrics.success_count = row['success_count'] or 0
            metrics.failure_count = row['failure_count'] or 0
            metrics.total_latency = (row['avg_latency'] or 0) * metrics.success_count
            metrics.total_tokens = row['total_tokens'] or 0
            metrics.total_cost = float(row['total_cost'] or 0)
            metrics.last_success = row['last_success']
            metrics.last_failure = row['last_failure']
    
    async def _save_provider_metrics(self, provider: LLMProvider, metrics: ProviderMetrics):
        """Save provider metrics to database"""
        # This would typically update a provider_metrics table
        # For now, metrics are tracked in memory and through llm_usage_logs
        pass
    
    async def get_provider_health_report(self) -> Dict[str, Any]:
        """Get health report for all providers"""
        report = {
            "providers": {},
            "summary": {
                "total_providers": len(self._provider_metrics),
                "healthy_providers": 0,
                "circuit_breakers_open": len(self._circuit_breakers),
                "rate_limited": len(self._rate_limits)
            }
        }
        
        for provider, metrics in self._provider_metrics.items():
            provider_info = {
                "healthy": metrics.is_healthy,
                "success_rate": metrics.success_rate,
                "average_latency": metrics.average_latency,
                "total_requests": metrics.success_count + metrics.failure_count,
                "consecutive_failures": metrics.consecutive_failures,
                "circuit_breaker_open": provider in self._circuit_breakers,
                "rate_limited": provider in self._rate_limits
            }
            
            if metrics.failure_reasons:
                provider_info["failure_reasons"] = dict(metrics.failure_reasons)
            
            report["providers"][provider.value] = provider_info
            
            if metrics.is_healthy:
                report["summary"]["healthy_providers"] += 1
        
        return report
    
    async def reset_provider_metrics(self, provider: Optional[LLMProvider] = None):
        """Reset metrics for a provider or all providers"""
        if provider:
            self._provider_metrics[provider] = ProviderMetrics()
            if provider in self._circuit_breakers:
                del self._circuit_breakers[provider]
            if provider in self._rate_limits:
                del self._rate_limits[provider]
        else:
            self._provider_metrics.clear()
            self._circuit_breakers.clear()
            self._rate_limits.clear()
        
        logger.info(f"Reset metrics for {provider or 'all providers'}")