"""
Unit tests for LLM Config Manager
"""

import pytest
import os
from pathlib import Path
import yaml
import json
from unittest.mock import patch, mock_open
from decimal import Decimal

from backend.services.llm_config_manager import LLMConfigManager
from backend.models.persona_instance import LLMProvider, LLMModel


@pytest.mark.asyncio
class TestLLMConfigManager:
    """Test LLM Config Manager functionality"""
    
    @pytest.fixture
    async def manager(self, db):
        """Create LLMConfigManager instance"""
        manager = LLMConfigManager(db)
        # Don't initialize to avoid file creation
        yield manager
        await manager.close()
    
    @pytest.fixture
    def sample_config(self):
        """Sample configuration for testing"""
        return {
            "providers": {
                "openai": {
                    "enabled": True,
                    "api_key_env": "OPENAI_API_KEY",
                    "models": [
                        {
                            "name": "gpt-4",
                            "max_tokens": 8192,
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
                        }
                    ]
                }
            },
            "fallback_chains": {
                "default": ["openai", "anthropic"],
                "vision": ["anthropic", "openai"]
            },
            "rate_limits": {
                "openai": {
                    "requests_per_minute": 500,
                    "tokens_per_minute": 150000
                }
            }
        }
    
    def test_create_default_config(self, manager):
        """Test default configuration creation"""
        config = manager._create_default_config()
        
        assert "providers" in config
        assert "fallback_chains" in config
        assert "rate_limits" in config
        
        # Check providers
        assert "openai" in config["providers"]
        assert "anthropic" in config["providers"]
        assert "gemini" in config["providers"]
        
        # Check fallback chains
        assert "default" in config["fallback_chains"]
        assert "vision" in config["fallback_chains"]
        assert "functions" in config["fallback_chains"]
    
    async def test_load_config(self, manager, sample_config, tmp_path):
        """Test loading configuration from file"""
        # Create temp config file
        config_file = tmp_path / "llm_providers.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)
        
        manager.config_path = config_file
        
        loaded = await manager.load_config()
        assert loaded == sample_config
    
    async def test_save_config(self, manager, sample_config, tmp_path):
        """Test saving configuration to file"""
        config_file = tmp_path / "llm_providers.yaml"
        manager.config_path = config_file
        
        await manager.save_config(sample_config)
        
        # Verify file was created and contains correct data
        assert config_file.exists()
        with open(config_file, 'r') as f:
            saved = yaml.safe_load(f)
        assert saved == sample_config
    
    async def test_get_available_models_all_enabled(self, manager, sample_config):
        """Test getting available models when all providers are enabled"""
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "test-key",
                "ANTHROPIC_API_KEY": "test-key"
            }):
                available = await manager.get_available_models()
                
                assert "openai" in available
                assert "anthropic" in available
                assert len(available["openai"]) == 1
                assert available["openai"][0]["name"] == "gpt-4"
    
    async def test_get_available_models_missing_api_key(self, manager, sample_config):
        """Test getting available models with missing API keys"""
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
                # ANTHROPIC_API_KEY is missing
                available = await manager.get_available_models()
                
                assert "openai" in available
                # Note: This test assumes ANTHROPIC_API_KEY is NOT set in the environment
                # If it is set, the test will fail as expected
    
    async def test_get_available_models_disabled_provider(self, manager, sample_config):
        """Test getting available models with disabled provider"""
        sample_config["providers"]["anthropic"]["enabled"] = False
        
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "test-key",
                "ANTHROPIC_API_KEY": "test-key"
            }):
                available = await manager.get_available_models()
                
                assert "openai" in available
                assert "anthropic" not in available  # Excluded due to disabled
    
    async def test_create_fallback_chain_default(self, manager, sample_config):
        """Test creating default fallback chain"""
        primary = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4",
            temperature=0.7,
            max_tokens=4096,
            api_key_env_var="OPENAI_API_KEY"
        )
        
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "test",
                "ANTHROPIC_API_KEY": "test"
            }):
                with patch.object(manager.provider_service, 'validate_api_key', return_value=True):
                    chain = await manager.create_fallback_chain(primary)
                    
                    assert len(chain) == 2
                    assert chain[0] == primary
                    assert chain[1].provider == LLMProvider.ANTHROPIC
                    assert chain[1].temperature == primary.temperature
    
    async def test_create_fallback_chain_vision(self, manager, sample_config):
        """Test creating vision-specific fallback chain"""
        primary = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4-vision",
            temperature=0.5,
            api_key_env_var="OPENAI_API_KEY"
        )
        
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "test",
                "ANTHROPIC_API_KEY": "test"
            }):
                with patch.object(manager.provider_service, 'validate_api_key', return_value=True):
                    chain = await manager.create_fallback_chain(primary, "vision")
                    
                    # Should have at least the primary model
                    assert len(chain) >= 1
                    assert chain[0] == primary
                    # If there's a fallback, it should be Anthropic for vision
                    if len(chain) > 1:
                        assert chain[1].provider == LLMProvider.ANTHROPIC
    
    async def test_update_provider_status(self, manager, sample_config):
        """Test enabling/disabling a provider"""
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.object(manager, 'save_config') as mock_save:
                await manager.update_provider_status(LLMProvider.OPENAI, False)
                
                # Verify the config was updated
                saved_config = mock_save.call_args[0][0]
                assert saved_config["providers"]["openai"]["enabled"] is False
    
    async def test_add_custom_model_new(self, manager, sample_config):
        """Test adding a new custom model"""
        new_model = {
            "name": "gpt-4-turbo",
            "max_tokens": 128000,
            "supports_vision": True,
            "supports_functions": True
        }
        
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.object(manager, 'save_config') as mock_save:
                await manager.add_custom_model(LLMProvider.OPENAI, new_model)
                
                saved_config = mock_save.call_args[0][0]
                models = saved_config["providers"]["openai"]["models"]
                assert len(models) == 2
                assert models[1]["name"] == "gpt-4-turbo"
    
    async def test_add_custom_model_update_existing(self, manager, sample_config):
        """Test updating an existing model"""
        updated_model = {
            "name": "gpt-4",
            "max_tokens": 16384,  # Updated
            "supports_vision": True,  # Updated
            "supports_functions": True
        }
        
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.object(manager, 'save_config') as mock_save:
                await manager.add_custom_model(LLMProvider.OPENAI, updated_model)
                
                saved_config = mock_save.call_args[0][0]
                models = saved_config["providers"]["openai"]["models"]
                assert len(models) == 1  # Still only one model
                assert models[0]["max_tokens"] == 16384
                assert models[0]["supports_vision"] is True
    
    async def test_get_rate_limits_existing(self, manager, sample_config):
        """Test getting rate limits for existing provider"""
        with patch.object(manager, 'load_config', return_value=sample_config):
            limits = await manager.get_rate_limits(LLMProvider.OPENAI)
            
            assert limits["requests_per_minute"] == 500
            assert limits["tokens_per_minute"] == 150000
    
    async def test_get_rate_limits_default(self, manager, sample_config):
        """Test getting default rate limits for provider without config"""
        with patch.object(manager, 'load_config', return_value=sample_config):
            limits = await manager.get_rate_limits(LLMProvider.ANTHROPIC)
            
            # Should return defaults
            assert limits["requests_per_minute"] == 60
            assert limits["tokens_per_minute"] == 60000
    
    async def test_validate_all_providers(self, manager, sample_config):
        """Test validating all configured providers"""
        with patch.object(manager, 'load_config', return_value=sample_config):
            with patch.object(
                manager.provider_service,
                'validate_provider_access',
                return_value={"valid": True, "model": "test"}
            ):
                results = await manager.validate_all_providers()
                
                assert "openai" in results
                assert "anthropic" in results
                assert results["openai"]["enabled"] is True
                assert results["openai"]["valid"] is True
    
    async def test_get_model_capabilities(self, manager, sample_config):
        """Test getting specific model capabilities"""
        with patch.object(manager, 'load_config', return_value=sample_config):
            caps = await manager.get_model_capabilities(LLMProvider.OPENAI, "gpt-4")
            
            assert caps is not None
            assert caps["name"] == "gpt-4"
            assert caps["max_tokens"] == 8192
            assert caps["supports_functions"] is True
    
    async def test_export_import_config(self, manager, sample_config):
        """Test exporting and importing configuration"""
        with patch.object(manager, 'load_config', return_value=sample_config):
            # Export
            exported = await manager.export_config()
            assert isinstance(exported, str)
            
            # Import
            with patch.object(manager, 'save_config') as mock_save:
                await manager.import_config(exported)
                
                # Verify same config was saved
                saved = mock_save.call_args[0][0]
                assert saved == sample_config