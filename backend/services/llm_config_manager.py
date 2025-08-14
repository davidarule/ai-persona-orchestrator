"""
Manager for LLM provider configurations and fallback chains
"""

import os
from typing import List, Dict, Any, Optional
from uuid import UUID
import yaml
import json
from pathlib import Path

from backend.models.persona_instance import LLMProvider, LLMModel
from backend.services.database import DatabaseManager
from backend.services.llm_provider_service import LLMProviderService


class LLMConfigManager:
    """Manages LLM provider configurations and fallback strategies"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.provider_service = LLMProviderService(db_manager)
        self.config_path = Path("config/llm_providers.yaml")
    
    async def initialize(self):
        """Initialize the configuration manager"""
        await self.provider_service.initialize()
        await self._ensure_config_exists()
    
    async def close(self):
        """Clean up resources"""
        await self.provider_service.close()
    
    async def _ensure_config_exists(self):
        """Ensure the LLM provider config file exists"""
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            default_config = self._create_default_config()
            with open(self.config_path, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False)
    
    def _create_default_config(self) -> Dict[str, Any]:
        """Create default LLM provider configuration"""
        return {
            "providers": {
                "openai": {
                    "enabled": True,
                    "api_key_env": "OPENAI_API_KEY",
                    "models": [
                        {
                            "name": "gpt-4-turbo-preview",
                            "max_tokens": 128000,
                            "supports_vision": True,
                            "supports_functions": True
                        },
                        {
                            "name": "gpt-4",
                            "max_tokens": 8192,
                            "supports_vision": False,
                            "supports_functions": True
                        },
                        {
                            "name": "gpt-3.5-turbo",
                            "max_tokens": 16385,
                            "supports_vision": False,
                            "supports_functions": True
                        }
                    ]
                },
                "anthropic": {
                    "enabled": True,
                    "api_key_env": "ANTHROPIC_API_KEY",
                    "models": [
                        {
                            "name": "claude-3-opus-20240229",
                            "max_tokens": 200000,
                            "supports_vision": True,
                            "supports_functions": False
                        },
                        {
                            "name": "claude-3-sonnet-20240229",
                            "max_tokens": 200000,
                            "supports_vision": True,
                            "supports_functions": False
                        },
                        {
                            "name": "claude-3-haiku-20240307",
                            "max_tokens": 200000,
                            "supports_vision": True,
                            "supports_functions": False
                        }
                    ]
                },
                "gemini": {
                    "enabled": True,
                    "api_key_env": "GEMINI_API_KEY",
                    "models": [
                        {
                            "name": "gemini-pro",
                            "max_tokens": 32760,
                            "supports_vision": False,
                            "supports_functions": True
                        },
                        {
                            "name": "gemini-pro-vision",
                            "max_tokens": 32760,
                            "supports_vision": True,
                            "supports_functions": True
                        }
                    ]
                },
                "grok": {
                    "enabled": False,
                    "api_key_env": "GROK_API_KEY",
                    "models": [
                        {
                            "name": "grok-1",
                            "max_tokens": 100000,
                            "supports_vision": False,
                            "supports_functions": True
                        }
                    ]
                },
                "azure_openai": {
                    "enabled": False,
                    "api_key_env": "AZURE_OPENAI_API_KEY",
                    "resource_env": "AZURE_OPENAI_RESOURCE",
                    "deployment_env": "AZURE_OPENAI_DEPLOYMENT",
                    "models": []
                }
            },
            "fallback_chains": {
                "default": ["openai", "anthropic", "gemini"],
                "vision": ["openai", "anthropic", "gemini"],
                "functions": ["openai", "gemini"],
                "long_context": ["anthropic", "gemini", "openai"]
            },
            "rate_limits": {
                "openai": {
                    "requests_per_minute": 500,
                    "tokens_per_minute": 150000
                },
                "anthropic": {
                    "requests_per_minute": 50,
                    "tokens_per_minute": 100000
                },
                "gemini": {
                    "requests_per_minute": 60,
                    "tokens_per_minute": 60000
                }
            }
        }
    
    async def load_config(self) -> Dict[str, Any]:
        """Load LLM provider configuration from file"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)
    
    async def save_config(self, config: Dict[str, Any]) -> None:
        """Save LLM provider configuration to file"""
        with open(self.config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
    
    async def get_available_models(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all available models grouped by provider"""
        config = await self.load_config()
        available = {}
        
        for provider_name, provider_config in config["providers"].items():
            if not provider_config.get("enabled", False):
                continue
            
            # Check if API key is available
            api_key_env = provider_config.get("api_key_env")
            if api_key_env and not os.getenv(api_key_env):
                continue
            
            available[provider_name] = provider_config.get("models", [])
        
        return available
    
    async def create_fallback_chain(
        self,
        primary_model: LLMModel,
        chain_type: str = "default"
    ) -> List[LLMModel]:
        """Create a fallback chain of LLM models"""
        config = await self.load_config()
        chain_names = config["fallback_chains"].get(chain_type, ["openai", "anthropic"])
        
        fallback_models = [primary_model]
        
        for provider_name in chain_names:
            # Skip if it's the same as primary
            if provider_name == primary_model.provider.value:
                continue
            
            provider_config = config["providers"].get(provider_name, {})
            if not provider_config.get("enabled", False):
                continue
            
            # Get the best model from this provider
            models = provider_config.get("models", [])
            if models:
                model_info = models[0]  # Take the most capable model
                
                try:
                    provider = LLMProvider(provider_name)
                    fallback_model = LLMModel(
                        provider=provider,
                        model_name=model_info["name"],
                        temperature=primary_model.temperature,
                        max_tokens=min(
                            primary_model.max_tokens or model_info["max_tokens"],
                            model_info["max_tokens"]
                        ),
                        api_key_env_var=provider_config["api_key_env"]
                    )
                    
                    # Validate the model has API key
                    if self.provider_service.validate_api_key(fallback_model):
                        fallback_models.append(fallback_model)
                except ValueError:
                    # Invalid provider name
                    continue
        
        return fallback_models
    
    async def update_provider_status(
        self,
        provider: LLMProvider,
        enabled: bool
    ) -> None:
        """Enable or disable a provider"""
        config = await self.load_config()
        
        if provider.value in config["providers"]:
            config["providers"][provider.value]["enabled"] = enabled
            await self.save_config(config)
    
    async def add_custom_model(
        self,
        provider: LLMProvider,
        model_info: Dict[str, Any]
    ) -> None:
        """Add a custom model configuration"""
        config = await self.load_config()
        
        if provider.value in config["providers"]:
            models = config["providers"][provider.value].get("models", [])
            
            # Check if model already exists
            for existing in models:
                if existing["name"] == model_info["name"]:
                    # Update existing
                    existing.update(model_info)
                    await self.save_config(config)
                    return
            
            # Add new model
            models.append(model_info)
            config["providers"][provider.value]["models"] = models
            await self.save_config(config)
    
    async def get_rate_limits(self, provider: LLMProvider) -> Dict[str, int]:
        """Get rate limits for a provider"""
        config = await self.load_config()
        return config["rate_limits"].get(
            provider.value,
            {"requests_per_minute": 60, "tokens_per_minute": 60000}
        )
    
    async def update_rate_limits(
        self,
        provider: LLMProvider,
        limits: Dict[str, int]
    ) -> None:
        """Update rate limits for a provider"""
        config = await self.load_config()
        config["rate_limits"][provider.value] = limits
        await self.save_config(config)
    
    async def validate_all_providers(self) -> Dict[str, Dict[str, Any]]:
        """Validate all configured providers"""
        config = await self.load_config()
        results = {}
        
        for provider_name, provider_config in config["providers"].items():
            if not provider_config.get("enabled", False):
                results[provider_name] = {
                    "enabled": False,
                    "valid": False,
                    "error": "Provider is disabled"
                }
                continue
            
            try:
                provider = LLMProvider(provider_name)
                models = provider_config.get("models", [])
                
                if models:
                    # Test with the first model
                    test_model = LLMModel(
                        provider=provider,
                        model_name=models[0]["name"],
                        temperature=0.7,
                        api_key_env_var=provider_config["api_key_env"]
                    )
                    
                    validation = await self.provider_service.validate_provider_access(test_model)
                    results[provider_name] = {
                        "enabled": True,
                        **validation
                    }
                else:
                    results[provider_name] = {
                        "enabled": True,
                        "valid": False,
                        "error": "No models configured"
                    }
                    
            except Exception as e:
                results[provider_name] = {
                    "enabled": True,
                    "valid": False,
                    "error": str(e)
                }
        
        return results
    
    async def get_model_capabilities(
        self,
        provider: LLMProvider,
        model_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get capabilities of a specific model"""
        config = await self.load_config()
        
        if provider.value in config["providers"]:
            models = config["providers"][provider.value].get("models", [])
            for model in models:
                if model["name"] == model_name:
                    return model
        
        return None
    
    async def export_config(self) -> str:
        """Export configuration as JSON string"""
        config = await self.load_config()
        return json.dumps(config, indent=2)
    
    async def import_config(self, config_json: str) -> None:
        """Import configuration from JSON string"""
        config = json.loads(config_json)
        await self.save_config(config)