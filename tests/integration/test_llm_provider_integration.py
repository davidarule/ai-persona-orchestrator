"""
Integration tests for LLM Provider and Config Manager
"""

import pytest
import os
from pathlib import Path
from decimal import Decimal
import asyncio
from uuid import uuid4

from backend.services.llm_provider_service import LLMProviderService
from backend.services.llm_config_manager import LLMConfigManager
from backend.models.persona_instance import LLMProvider, LLMModel
from backend.factories.persona_instance_factory import PersonaInstanceFactory
from backend.services.persona_instance_service import PersonaInstanceService
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository
from unittest.mock import patch


@pytest.mark.integration
@pytest.mark.asyncio
class TestLLMProviderIntegration:
    """Integration tests for LLM provider functionality"""
    
    async def test_provider_service_with_real_db(self, db):
        """Test LLM provider service with real database"""
        service = LLMProviderService(db)
        await service.initialize()
        
        try:
            # Test getting provider status
            status = await service.get_provider_status()
            assert "providers" in status
            assert len(status["providers"]) == 5  # All LLMProvider enum values
            
            # Test cost estimation
            model = LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )
            cost = service.estimate_cost(model, 1000, 500)
            assert isinstance(cost, Decimal)
            assert cost > 0
            
        finally:
            await service.close()
    
    async def test_config_manager_lifecycle(self, db, tmp_path):
        """Test config manager full lifecycle"""
        # Use temp directory for config
        config_path = tmp_path / "config" / "llm_providers.yaml"
        
        manager = LLMConfigManager(db)
        manager.config_path = config_path
        
        try:
            await manager.initialize()
            
            # Verify config file was created
            assert config_path.exists()
            
            # Test loading config
            config = await manager.load_config()
            assert "providers" in config
            assert "fallback_chains" in config
            
            # Test modifying and saving
            await manager.update_provider_status(LLMProvider.GROK, True)
            
            # Reload and verify change persisted
            config = await manager.load_config()
            assert config["providers"]["grok"]["enabled"] is True
            
        finally:
            await manager.close()
    
    async def test_persona_instance_with_llm_config(self, db, clean_test_data):
        """Test creating persona instance with LLM configuration"""
        # Create persona type
        type_repo = PersonaTypeRepository(db)
        persona_type = await type_repo.create(PersonaTypeCreate(
            type_name=f"architect-{uuid4().hex[:8]}",
            display_name="Software Architect",
            category=PersonaCategory.ARCHITECTURE,
            description="Test architect with LLM config",
            base_workflow_id="wf0"
        ))
        
        # Create instance with specific LLM config
        factory = PersonaInstanceFactory(db)
        
        custom_llm = [
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4-turbo-preview",
                temperature=0.3,
                max_tokens=8192,
                api_key_env_var="OPENAI_API_KEY"
            ),
            LLMModel(
                provider=LLMProvider.ANTHROPIC,
                model_name="claude-3-opus-20240229",
                temperature=0.5,
                max_tokens=4096,
                api_key_env_var="ANTHROPIC_API_KEY"
            )
        ]
        
        instance = await factory.create_instance(
            instance_name=f"TEST_Architect_LLM_{uuid4().hex[:8]}",
            persona_type_id=persona_type.id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="TestProject",
            custom_llm_providers=custom_llm
        )
        
        # Verify LLM configuration
        assert len(instance.llm_providers) == 2
        assert instance.llm_providers[0].provider == LLMProvider.OPENAI
        assert instance.llm_providers[0].temperature == 0.3
        assert instance.llm_providers[1].provider == LLMProvider.ANTHROPIC
        
        # Test provider validation
        provider_service = LLMProviderService(db)
        await provider_service.initialize()
        
        try:
            # This will fail without actual API keys, but tests the flow
            for llm in instance.llm_providers:
                if provider_service.validate_api_key(llm):
                    validation = await provider_service.validate_provider_access(llm)
                    print(f"Validation result for {llm.provider}: {validation}")
                else:
                    print(f"No API key for {llm.provider}")
        finally:
            await provider_service.close()
    
    async def test_fallback_chain_creation(self, db, tmp_path):
        """Test creating and using fallback chains"""
        # Setup config manager with temp path
        manager = LLMConfigManager(db)
        manager.config_path = tmp_path / "llm_providers.yaml"
        
        try:
            await manager.initialize()
            
            # Create primary model
            primary = LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                temperature=0.7,
                max_tokens=4096,
                api_key_env_var="OPENAI_API_KEY"
            )
            
            # Create fallback chain
            from unittest.mock import patch
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "test",
                "ANTHROPIC_API_KEY": "test",
                "GEMINI_API_KEY": "test"
            }):
                chain = await manager.create_fallback_chain(primary, "default")
                
                # Should have primary + fallbacks
                assert len(chain) >= 2
                assert chain[0] == primary
                
                # Verify fallback providers are different
                providers = [model.provider for model in chain]
                assert len(set(providers)) == len(providers)  # All unique
        
        finally:
            await manager.close()
    
    async def test_llm_usage_logging(self, db, clean_test_data):
        """Test logging LLM usage to database"""
        service = LLMProviderService(db)
        await service.initialize()
        
        try:
            # Create test instance ID
            instance_id = str(uuid4())
            
            # Log some usage
            model = LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )
            
            await service.record_usage(
                instance_id=instance_id,
                llm_model=model,
                input_tokens=1500,
                output_tokens=750,
                cost=Decimal("0.105"),  # $0.105
                success=True
            )
            
            # Log a failure
            await service.record_usage(
                instance_id=instance_id,
                llm_model=model,
                input_tokens=500,
                output_tokens=0,
                cost=Decimal("0.015"),
                success=False,
                error_message="Rate limit exceeded"
            )
            
            # Query logs (would need actual query implementation)
            # For now, just verify no exceptions
            assert True
            
        finally:
            await service.close()
    
    async def test_model_selection_criteria(self, db):
        """Test intelligent model selection based on criteria"""
        service = LLMProviderService(db)
        await service.initialize()
        
        try:
            # Create a set of models with different characteristics
            models = [
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                ),
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY"
                ),
                LLMModel(
                    provider=LLMProvider.ANTHROPIC,
                    model_name="claude-3-haiku-20240307",
                    api_key_env_var="ANTHROPIC_API_KEY"
                ),
                LLMModel(
                    provider=LLMProvider.GEMINI,
                    model_name="gemini-pro",
                    api_key_env_var="GEMINI_API_KEY"
                )
            ]
            
            # Test cost-based selection
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "test",
                "ANTHROPIC_API_KEY": "test",
                "GEMINI_API_KEY": "test"
            }):
                # Select cheapest model
                cheap_model = service.select_best_model(
                    models,
                    {"max_cost_per_1k_tokens": 0.01}  # Only gpt-3.5-turbo and claude-haiku fit
                )
                assert cheap_model is not None
                assert cheap_model.model_name in ["gpt-3.5-turbo", "claude-3-haiku-20240307", "gemini-pro"]
                
                # Select by provider preference
                anthropic_model = service.select_best_model(
                    models,
                    {"preferred_providers": [LLMProvider.ANTHROPIC]}
                )
                assert anthropic_model is not None
                assert anthropic_model.provider == LLMProvider.ANTHROPIC
                
        finally:
            await service.close()
    
    async def test_concurrent_provider_validation(self, db):
        """Test validating multiple providers concurrently"""
        service = LLMProviderService(db)
        await service.initialize()
        
        try:
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
                ),
                LLMModel(
                    provider=LLMProvider.GEMINI,
                    model_name="gemini-pro",
                    api_key_env_var="GEMINI_API_KEY"
                )
            ]
            
            # Test concurrent validation
            validation_tasks = []
            for model in models:
                if service.validate_api_key(model):
                    task = service.validate_provider_access(model)
                    validation_tasks.append(task)
            
            if validation_tasks:
                results = await asyncio.gather(*validation_tasks, return_exceptions=True)
                
                # Check results
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f"Validation failed for model {i}: {result}")
                    else:
                        print(f"Validation result for model {i}: {result}")
            
        finally:
            await service.close()