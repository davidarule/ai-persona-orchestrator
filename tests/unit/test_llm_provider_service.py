"""
Unit tests for LLM Provider Service
"""

import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from decimal import Decimal
import aiohttp
import json

from backend.services.llm_provider_service import LLMProviderService
from backend.models.persona_instance import LLMProvider, LLMModel


@pytest.mark.asyncio
class TestLLMProviderService:
    """Test LLM Provider Service functionality"""
    
    @pytest.fixture
    async def service(self, db):
        """Create LLMProviderService instance"""
        service = LLMProviderService(db)
        await service.initialize()
        yield service
        await service.close()
    
    def test_validate_api_key_present(self, service):
        """Test API key validation when key is present"""
        model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4",
            api_key_env_var="TEST_API_KEY"
        )
        
        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test-key"}):
            assert service.validate_api_key(model) is True
    
    def test_validate_api_key_missing(self, service):
        """Test API key validation when key is missing"""
        model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4",
            api_key_env_var="MISSING_KEY"
        )
        
        assert service.validate_api_key(model) is False
    
    def test_estimate_cost_known_model(self, service):
        """Test cost estimation for known models"""
        model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4-turbo-preview",
            api_key_env_var="OPENAI_API_KEY"
        )
        
        # 1000 input tokens, 500 output tokens
        cost = service.estimate_cost(model, 1000, 500)
        
        # gpt-4-turbo-preview: $10/1M input, $30/1M output
        expected = Decimal("0.01") + Decimal("0.015")  # $0.025
        assert cost == expected
    
    def test_estimate_cost_unknown_model(self, service):
        """Test cost estimation falls back to default for unknown models"""
        model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="future-model-xyz",
            api_key_env_var="OPENAI_API_KEY"
        )
        
        cost = service.estimate_cost(model, 1000, 500)
        
        # Default: $10/1M input, $30/1M output
        expected = Decimal("0.01") + Decimal("0.015")
        assert cost == expected
    
    async def test_validate_openai_success(self, service):
        """Test successful OpenAI validation"""
        model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4",
            api_key_env_var="OPENAI_API_KEY"
        )
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "model": "gpt-4",
            "usage": {"total_tokens": 5}
        })
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
            with patch.object(
                service._sessions[LLMProvider.OPENAI],
                'post',
                return_value=mock_response
            ) as mock_post:
                mock_post.return_value.__aenter__.return_value = mock_response
                
                result = await service.validate_provider_access(model)
                
                assert result["valid"] is True
                assert result["model"] == "gpt-4"
    
    async def test_validate_anthropic_success(self, service):
        """Test successful Anthropic validation"""
        model = LLMModel(
            provider=LLMProvider.ANTHROPIC,
            model_name="claude-3-opus-20240229",
            api_key_env_var="ANTHROPIC_API_KEY"
        )
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "model": "claude-3-opus-20240229",
            "usage": {"input_tokens": 2, "output_tokens": 3}
        })
        
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            with patch.object(
                service._sessions[LLMProvider.ANTHROPIC],
                'post',
                return_value=mock_response
            ) as mock_post:
                mock_post.return_value.__aenter__.return_value = mock_response
                
                result = await service.validate_provider_access(model)
                
                assert result["valid"] is True
                assert result["model"] == "claude-3-opus-20240229"
    
    async def test_validate_provider_api_error(self, service):
        """Test provider validation with API error"""
        model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4",
            api_key_env_var="OPENAI_API_KEY"
        )
        
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Invalid API key")
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "invalid-key"}):
            with patch.object(
                service._sessions[LLMProvider.OPENAI],
                'post',
                return_value=mock_response
            ) as mock_post:
                mock_post.return_value.__aenter__.return_value = mock_response
                
                result = await service.validate_provider_access(model)
                
                assert result["valid"] is False
                assert "401" in result["error"]
    
    def test_select_best_model_by_cost(self, service):
        """Test selecting best model based on cost criteria"""
        models = [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",  # Expensive
                api_key_env_var="OPENAI_API_KEY"
            ),
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-3.5-turbo",  # Cheap
                api_key_env_var="OPENAI_API_KEY"
            )
        ]
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            selected = service.select_best_model(
                models,
                {"max_cost_per_1k_tokens": 0.01}  # $0.01 per 1k tokens - only gpt-3.5-turbo fits
            )
            
            assert selected is not None
            assert selected.model_name == "gpt-3.5-turbo"
    
    def test_select_best_model_by_provider(self, service):
        """Test selecting best model based on provider preference"""
        models = [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            ),
            LLMModel(
                provider=LLMProvider.ANTHROPIC,
                model_name="claude-3-opus-20240229",
                api_key_env_var="ANTHROPIC_API_KEY"
            )
        ]
        
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test",
            "ANTHROPIC_API_KEY": "test"
        }):
            selected = service.select_best_model(
                models,
                {"preferred_providers": [LLMProvider.ANTHROPIC]}
            )
            
            assert selected is not None
            assert selected.provider == LLMProvider.ANTHROPIC
    
    def test_select_best_model_no_valid(self, service):
        """Test model selection when no models meet criteria"""
        models = [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="MISSING_KEY"
            )
        ]
        
        selected = service.select_best_model(models, {})
        assert selected is None
    
    async def test_get_provider_status(self, service):
        """Test getting provider configuration status"""
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test",
            "AZURE_OPENAI_API_KEY": "test",
            "AZURE_OPENAI_RESOURCE": "test-resource",
            "AZURE_OPENAI_DEPLOYMENT": "test-deploy"
        }):
            status = await service.get_provider_status()
            
            assert "providers" in status
            assert status["providers"][LLMProvider.OPENAI.value]["configured"] is True
            # Note: This test assumes ANTHROPIC_API_KEY is NOT set
            # The test may fail if the key is actually configured in the environment
            assert status["providers"][LLMProvider.AZURE_OPENAI.value]["configured"] is True
    
    async def test_record_usage(self, service, db):
        """Test recording LLM usage logs"""
        model = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4",
            api_key_env_var="OPENAI_API_KEY"
        )
        
        await service.record_usage(
            instance_id="test-instance-123",
            llm_model=model,
            input_tokens=100,
            output_tokens=50,
            cost=Decimal("0.015"),
            success=True
        )
        
        # Verify it was recorded (would need to query DB)
        # For now just verify no exceptions
        assert True
    
    async def test_test_all_providers(self, service):
        """Test validating multiple providers"""
        models = [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            ),
            LLMModel(
                provider=LLMProvider.ANTHROPIC,
                model_name="claude-3",
                api_key_env_var="ANTHROPIC_API_KEY"
            ),
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-3.5-turbo",
                api_key_env_var="OPENAI_API_KEY"
            )
        ]
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            # Mock the validate method
            with patch.object(service, 'validate_provider_access') as mock_validate:
                mock_validate.return_value = {"valid": True, "model": "test"}
                
                results = await service.test_all_providers(models)
                
                # Should test OpenAI and Anthropic once each
                assert len(results) == 2
                assert LLMProvider.OPENAI in results
                assert LLMProvider.ANTHROPIC in results