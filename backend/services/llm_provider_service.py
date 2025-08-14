"""
Service for managing LLM provider configurations and interactions
"""

import os
from typing import Dict, Any, Optional, List
from decimal import Decimal
import asyncio
import aiohttp
import json
from datetime import datetime

from backend.models.persona_instance import LLMProvider, LLMModel
from backend.services.database import DatabaseManager


class LLMProviderService:
    """Service for managing LLM provider configurations and API interactions"""
    
    # Provider API endpoints
    PROVIDER_ENDPOINTS = {
        LLMProvider.OPENAI: "https://api.openai.com/v1/chat/completions",
        LLMProvider.ANTHROPIC: "https://api.anthropic.com/v1/messages",
        LLMProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        LLMProvider.GROK: "https://api.x.ai/v1/chat/completions",
        LLMProvider.AZURE_OPENAI: "https://{resource}.openai.azure.com/openai/deployments/{deployment}/chat/completions"
    }
    
    # Model pricing per 1M tokens (input/output)
    MODEL_PRICING = {
        # OpenAI
        "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
        "gpt-4": {"input": 30.00, "output": 60.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        
        # Anthropic
        "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        
        # Google Gemini
        "gemini-pro": {"input": 0.50, "output": 1.50},
        "gemini-pro-vision": {"input": 0.50, "output": 1.50},
        
        # Grok
        "grok-1": {"input": 20.00, "output": 60.00},
        
        # Default fallback
        "default": {"input": 10.00, "output": 30.00}
    }
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._sessions: Dict[LLMProvider, aiohttp.ClientSession] = {}
    
    async def initialize(self):
        """Initialize HTTP sessions for each provider"""
        for provider in LLMProvider:
            self._sessions[provider] = aiohttp.ClientSession()
    
    async def close(self):
        """Close all HTTP sessions"""
        for session in self._sessions.values():
            await session.close()
    
    def validate_api_key(self, llm_model: LLMModel) -> bool:
        """Validate that the API key environment variable is set"""
        api_key = os.getenv(llm_model.api_key_env_var)
        return api_key is not None and len(api_key) > 0
    
    def get_api_key(self, llm_model: LLMModel) -> Optional[str]:
        """Get API key from environment variable"""
        return os.getenv(llm_model.api_key_env_var)
    
    def estimate_cost(
        self,
        llm_model: LLMModel,
        input_tokens: int,
        output_tokens: int
    ) -> Decimal:
        """Estimate cost for a completion based on token counts"""
        pricing = self.MODEL_PRICING.get(
            llm_model.model_name,
            self.MODEL_PRICING["default"]
        )
        
        # Calculate cost (pricing is per 1M tokens)
        input_cost = Decimal(str(pricing["input"])) * input_tokens / 1_000_000
        output_cost = Decimal(str(pricing["output"])) * output_tokens / 1_000_000
        
        return input_cost + output_cost
    
    async def validate_provider_access(self, llm_model: LLMModel) -> Dict[str, Any]:
        """Validate access to a provider by making a test request"""
        if not self.validate_api_key(llm_model):
            return {
                "valid": False,
                "error": f"API key not found in environment variable: {llm_model.api_key_env_var}"
            }
        
        try:
            # Make a minimal test request
            if llm_model.provider == LLMProvider.OPENAI:
                return await self._validate_openai(llm_model)
            elif llm_model.provider == LLMProvider.ANTHROPIC:
                return await self._validate_anthropic(llm_model)
            elif llm_model.provider == LLMProvider.GEMINI:
                return await self._validate_gemini(llm_model)
            elif llm_model.provider == LLMProvider.GROK:
                return await self._validate_grok(llm_model)
            elif llm_model.provider == LLMProvider.AZURE_OPENAI:
                return await self._validate_azure_openai(llm_model)
            else:
                return {
                    "valid": False,
                    "error": f"Unknown provider: {llm_model.provider}"
                }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e)
            }
    
    async def _validate_openai(self, llm_model: LLMModel) -> Dict[str, Any]:
        """Validate OpenAI access"""
        api_key = self.get_api_key(llm_model)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Minimal test request
        data = {
            "model": llm_model.model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
            "temperature": 0
        }
        
        async with self._sessions[LLMProvider.OPENAI].post(
            self.PROVIDER_ENDPOINTS[LLMProvider.OPENAI],
            headers=headers,
            json=data
        ) as response:
            if response.status == 200:
                result = await response.json()
                return {
                    "valid": True,
                    "model": result.get("model"),
                    "usage": result.get("usage", {})
                }
            else:
                error_data = await response.text()
                return {
                    "valid": False,
                    "error": f"API error {response.status}: {error_data}"
                }
    
    async def _validate_anthropic(self, llm_model: LLMModel) -> Dict[str, Any]:
        """Validate Anthropic access"""
        api_key = self.get_api_key(llm_model)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        data = {
            "model": llm_model.model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5
        }
        
        async with self._sessions[LLMProvider.ANTHROPIC].post(
            self.PROVIDER_ENDPOINTS[LLMProvider.ANTHROPIC],
            headers=headers,
            json=data
        ) as response:
            if response.status == 200:
                result = await response.json()
                return {
                    "valid": True,
                    "model": result.get("model"),
                    "usage": result.get("usage", {})
                }
            else:
                error_data = await response.text()
                return {
                    "valid": False,
                    "error": f"API error {response.status}: {error_data}"
                }
    
    async def _validate_gemini(self, llm_model: LLMModel) -> Dict[str, Any]:
        """Validate Google Gemini access"""
        api_key = self.get_api_key(llm_model)
        url = self.PROVIDER_ENDPOINTS[LLMProvider.GEMINI].format(
            model=llm_model.model_name
        ) + f"?key={api_key}"
        
        data = {
            "contents": [{"parts": [{"text": "Hi"}]}],
            "generationConfig": {"maxOutputTokens": 5}
        }
        
        async with self._sessions[LLMProvider.GEMINI].post(
            url,
            json=data
        ) as response:
            if response.status == 200:
                result = await response.json()
                return {
                    "valid": True,
                    "model": llm_model.model_name,
                    "candidates": len(result.get("candidates", []))
                }
            else:
                error_data = await response.text()
                return {
                    "valid": False,
                    "error": f"API error {response.status}: {error_data}"
                }
    
    async def _validate_grok(self, llm_model: LLMModel) -> Dict[str, Any]:
        """Validate Grok access"""
        # Similar to OpenAI format
        return await self._validate_openai(llm_model)
    
    async def _validate_azure_openai(self, llm_model: LLMModel) -> Dict[str, Any]:
        """Validate Azure OpenAI access"""
        api_key = self.get_api_key(llm_model)
        
        # Azure requires additional config from environment
        resource = os.getenv("AZURE_OPENAI_RESOURCE")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        
        if not resource or not deployment:
            return {
                "valid": False,
                "error": "Missing AZURE_OPENAI_RESOURCE or AZURE_OPENAI_DEPLOYMENT environment variables"
            }
        
        url = self.PROVIDER_ENDPOINTS[LLMProvider.AZURE_OPENAI].format(
            resource=resource,
            deployment=deployment
        ) + f"?api-version={api_version}"
        
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json"
        }
        
        data = {
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
            "temperature": 0
        }
        
        async with self._sessions[LLMProvider.AZURE_OPENAI].post(
            url,
            headers=headers,
            json=data
        ) as response:
            if response.status == 200:
                result = await response.json()
                return {
                    "valid": True,
                    "model": deployment,
                    "usage": result.get("usage", {})
                }
            else:
                error_data = await response.text()
                return {
                    "valid": False,
                    "error": f"API error {response.status}: {error_data}"
                }
    
    async def test_all_providers(self, llm_models: List[LLMModel]) -> Dict[LLMProvider, Dict[str, Any]]:
        """Test all providers in a list of LLM models"""
        results = {}
        
        for model in llm_models:
            if model.provider not in results:
                results[model.provider] = await self.validate_provider_access(model)
        
        return results
    
    def select_best_model(
        self,
        llm_models: List[LLMModel],
        criteria: Dict[str, Any]
    ) -> Optional[LLMModel]:
        """
        Select the best model based on criteria
        
        Criteria can include:
        - max_cost_per_1k_tokens: Maximum acceptable cost
        - min_context_window: Minimum required context window
        - preferred_providers: List of preferred providers
        - required_capabilities: List of required capabilities
        """
        valid_models = []
        
        for model in llm_models:
            # Check API key availability
            if not self.validate_api_key(model):
                continue
            
            # Check cost criteria
            if "max_cost_per_1k_tokens" in criteria:
                pricing = self.MODEL_PRICING.get(
                    model.model_name,
                    self.MODEL_PRICING["default"]
                )
                avg_cost = (pricing["input"] + pricing["output"]) / 2 / 1000
                if avg_cost > criteria["max_cost_per_1k_tokens"]:
                    continue
            
            # Check provider preference
            if "preferred_providers" in criteria:
                if model.provider not in criteria["preferred_providers"]:
                    continue
            
            valid_models.append(model)
        
        # Return first valid model (they're already in priority order)
        return valid_models[0] if valid_models else None
    
    async def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all configured providers"""
        status = {
            "providers": {},
            "total_models": 0,
            "available_models": 0
        }
        
        # Check each provider
        for provider in LLMProvider:
            env_vars = self._get_provider_env_vars(provider)
            configured = all(os.getenv(var) is not None for var in env_vars)
            
            status["providers"][provider.value] = {
                "configured": configured,
                "required_env_vars": env_vars
            }
        
        return status
    
    def _get_provider_env_vars(self, provider: LLMProvider) -> List[str]:
        """Get required environment variables for a provider"""
        base_vars = {
            LLMProvider.OPENAI: ["OPENAI_API_KEY"],
            LLMProvider.ANTHROPIC: ["ANTHROPIC_API_KEY"],
            LLMProvider.GEMINI: ["GEMINI_API_KEY"],
            LLMProvider.GROK: ["GROK_API_KEY"],
            LLMProvider.AZURE_OPENAI: [
                "AZURE_OPENAI_API_KEY",
                "AZURE_OPENAI_RESOURCE",
                "AZURE_OPENAI_DEPLOYMENT"
            ]
        }
        return base_vars.get(provider, [])
    
    async def record_usage(
        self,
        instance_id: str,
        llm_model: LLMModel,
        input_tokens: int,
        output_tokens: int,
        cost: Decimal,
        success: bool,
        error_message: Optional[str] = None
    ) -> None:
        """Record LLM usage for tracking and analytics"""
        query = """
        INSERT INTO orchestrator.llm_usage_logs (
            instance_id, provider, model_name, input_tokens, output_tokens,
            total_cost, success, error_message, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        
        await self.db.execute_query(
            query,
            instance_id,
            llm_model.provider.value,
            llm_model.model_name,
            input_tokens,
            output_tokens,
            str(cost),
            success,
            error_message,
            datetime.utcnow()
        )