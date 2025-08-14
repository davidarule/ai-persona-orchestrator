"""
End-to-end tests for LLM Provider functionality
"""

import pytest
import os
from pathlib import Path
from decimal import Decimal
from uuid import uuid4
import asyncio

from backend.services.llm_provider_service import LLMProviderService
from backend.services.llm_config_manager import LLMConfigManager
from backend.models.persona_instance import LLMProvider, LLMModel, PersonaInstanceCreate
from backend.factories.persona_instance_factory import PersonaInstanceFactory
from backend.services.persona_instance_service import PersonaInstanceService
from backend.models.persona_type import PersonaTypeCreate, PersonaCategory
from backend.repositories.persona_repository import PersonaTypeRepository


@pytest.mark.e2e
@pytest.mark.asyncio
class TestLLMProviderE2E:
    """End-to-end tests simulating real-world LLM provider scenarios"""
    
    async def test_complete_llm_setup_workflow(self, db, tmp_path, clean_test_data):
        """Test complete workflow of setting up LLM providers for a project"""
        print("\n=== Complete LLM Provider Setup Workflow ===")
        
        # Step 1: Initialize LLM configuration
        config_manager = LLMConfigManager(db)
        config_manager.config_path = tmp_path / "llm_providers.yaml"
        await config_manager.initialize()
        
        provider_service = LLMProviderService(db)
        await provider_service.initialize()
        
        try:
            # Step 2: Configure providers based on available API keys
            print("\nStep 1: Checking available providers...")
            status = await provider_service.get_provider_status()
            
            available_providers = []
            for provider_name, info in status["providers"].items():
                if info["configured"]:
                    print(f"  ✓ {provider_name}: Configured")
                    available_providers.append(provider_name)
                else:
                    print(f"  ✗ {provider_name}: Missing API keys")
            
            # Step 3: Enable only available providers
            print("\nStep 2: Configuring provider settings...")
            for provider in LLMProvider:
                enabled = provider.value in available_providers
                await config_manager.update_provider_status(provider, enabled)
            
            # Step 4: Create persona types for the project
            print("\nStep 3: Creating persona types...")
            type_repo = PersonaTypeRepository(db)
            
            architect_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"lead-architect-{uuid4().hex[:8]}",
                display_name="Lead Architect",
                category=PersonaCategory.ARCHITECTURE,
                description="Lead architect with multi-model support",
                base_workflow_id="wf0"
            ))
            
            developer_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"senior-dev-{uuid4().hex[:8]}",
                display_name="Senior Developer",
                category=PersonaCategory.DEVELOPMENT,
                description="Senior developer with code generation focus",
                base_workflow_id="wf0"
            ))
            
            # Step 5: Create instances with appropriate LLM configurations
            print("\nStep 4: Creating persona instances with LLM configs...")
            factory = PersonaInstanceFactory(db)
            service = PersonaInstanceService(db)
            
            # Architect gets multiple high-end models
            architect_llms = []
            if "openai" in available_providers:
                architect_llms.append(LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4-turbo-preview",
                    temperature=0.7,
                    max_tokens=8192,
                    api_key_env_var="OPENAI_API_KEY"
                ))
            
            if "anthropic" in available_providers:
                architect_llms.append(LLMModel(
                    provider=LLMProvider.ANTHROPIC,
                    model_name="claude-3-opus-20240229",
                    temperature=0.5,
                    max_tokens=4096,
                    api_key_env_var="ANTHROPIC_API_KEY"
                ))
            
            # Default fallback if no providers available
            if not architect_llms:
                architect_llms = [LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )]
            
            architect_instance = await factory.create_instance(
                instance_name=f"TEST_Lead_Architect_{uuid4().hex[:8]}",
                persona_type_id=architect_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="AI-Personas-Test",
                custom_llm_providers=architect_llms,
                custom_spend_limits={"daily": Decimal("150.00"), "monthly": Decimal("3000.00")},
                priority_level=10
            )
            
            print(f"  Created architect with {len(architect_instance.llm_providers)} LLM providers")
            
            # Developer gets cost-effective models
            dev_llms = []
            if "openai" in available_providers:
                dev_llms.append(LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    temperature=0.7,
                    max_tokens=4096,
                    api_key_env_var="OPENAI_API_KEY"
                ))
            
            if not dev_llms:
                dev_llms = [LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-3.5-turbo",
                    api_key_env_var="OPENAI_API_KEY"
                )]
            
            developer_instance = await factory.create_instance(
                instance_name=f"TEST_Senior_Dev_{uuid4().hex[:8]}",
                persona_type_id=developer_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="AI-Personas-Test",
                custom_llm_providers=dev_llms,
                custom_spend_limits={"daily": Decimal("50.00"), "monthly": Decimal("1000.00")},
                priority_level=8
            )
            
            print(f"  Created developer with {len(developer_instance.llm_providers)} LLM providers")
            
            # Step 6: Validate provider access
            print("\nStep 5: Validating LLM provider access...")
            
            all_models = architect_instance.llm_providers + developer_instance.llm_providers
            validation_results = await provider_service.test_all_providers(all_models)
            
            for provider, result in validation_results.items():
                if result.get("valid"):
                    print(f"  ✓ {provider}: Valid")
                else:
                    print(f"  ✗ {provider}: {result.get('error', 'Invalid')}")
            
            # Step 7: Simulate usage and cost tracking
            print("\nStep 6: Simulating usage...")
            
            # Architect does complex design work
            await provider_service.record_usage(
                instance_id=str(architect_instance.id),
                llm_model=architect_instance.llm_providers[0],
                input_tokens=5000,
                output_tokens=2500,
                cost=Decimal("0.225"),  # High-end model cost
                success=True
            )
            
            await service.record_spend(
                architect_instance.id,
                Decimal("0.225"),
                "System architecture design"
            )
            
            # Developer does code generation
            await provider_service.record_usage(
                instance_id=str(developer_instance.id),
                llm_model=developer_instance.llm_providers[0],
                input_tokens=2000,
                output_tokens=1500,
                cost=Decimal("0.00525"),  # Cheaper model
                success=True
            )
            
            await service.record_spend(
                developer_instance.id,
                Decimal("0.00525"),
                "Code generation task"
            )
            
            # Step 8: Check spend tracking
            print("\nStep 7: Checking spend tracking...")
            
            arch_updated = await service.get_instance(architect_instance.id)
            dev_updated = await service.get_instance(developer_instance.id)
            
            print(f"  Architect daily spend: ${arch_updated.current_spend_daily} "
                  f"({arch_updated.spend_percentage_daily:.1f}% of limit)")
            print(f"  Developer daily spend: ${dev_updated.current_spend_daily} "
                  f"({dev_updated.spend_percentage_daily:.1f}% of limit)")
            
            # Step 9: Test fallback chains
            print("\nStep 8: Testing fallback chain creation...")
            
            primary_model = architect_instance.llm_providers[0]
            fallback_chain = await config_manager.create_fallback_chain(primary_model, "default")
            
            print(f"  Created fallback chain with {len(fallback_chain)} models:")
            for i, model in enumerate(fallback_chain):
                print(f"    {i+1}. {model.provider.value}: {model.model_name}")
            
            print("\nWorkflow completed successfully!")
            
        finally:
            await provider_service.close()
            await config_manager.close()
    
    async def test_multi_provider_failover_scenario(self, db, tmp_path, clean_test_data):
        """Test failover between multiple LLM providers"""
        print("\n=== Multi-Provider Failover Scenario ===")
        
        # Setup
        config_manager = LLMConfigManager(db)
        config_manager.config_path = tmp_path / "llm_providers.yaml"
        await config_manager.initialize()
        
        provider_service = LLMProviderService(db)
        await provider_service.initialize()
        
        try:
            # Create a critical persona that needs high availability
            type_repo = PersonaTypeRepository(db)
            critical_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"incident-responder-{uuid4().hex[:8]}",
                display_name="Incident Responder",
                category=PersonaCategory.OPERATIONS,
                description="24/7 incident response with failover",
                base_workflow_id="wf11"  # monitoring workflow
            ))
            
            # Configure with multiple providers for failover
            factory = PersonaInstanceFactory(db)
            
            failover_llms = [
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    temperature=0.3,  # Low temp for consistency
                    max_tokens=4096,
                    api_key_env_var="OPENAI_API_KEY"
                ),
                LLMModel(
                    provider=LLMProvider.ANTHROPIC,
                    model_name="claude-3-sonnet-20240229",
                    temperature=0.3,
                    max_tokens=4096,
                    api_key_env_var="ANTHROPIC_API_KEY"
                ),
                LLMModel(
                    provider=LLMProvider.GEMINI,
                    model_name="gemini-pro",
                    temperature=0.3,
                    max_tokens=4096,
                    api_key_env_var="GEMINI_API_KEY"
                )
            ]
            
            incident_instance = await factory.create_instance(
                instance_name=f"TEST_Incident_Responder_{uuid4().hex[:8]}",
                persona_type_id=critical_type.id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="Production-Support",
                custom_llm_providers=failover_llms,
                custom_spend_limits={"daily": Decimal("200.00"), "monthly": Decimal("4000.00")},
                priority_level=10,  # Highest priority
                max_concurrent_tasks=1  # Focus on one incident at a time
            )
            
            print(f"Created incident responder with {len(incident_instance.llm_providers)} failover providers")
            
            # Simulate primary provider failure
            print("\nSimulating provider failures and failovers...")
            
            for i, llm_model in enumerate(incident_instance.llm_providers):
                print(f"\nAttempting provider {i+1}: {llm_model.provider.value}")
                
                if provider_service.validate_api_key(llm_model):
                    # Try to use the provider
                    validation = await provider_service.validate_provider_access(llm_model)
                    
                    if validation.get("valid"):
                        print(f"  ✓ Success! Using {llm_model.provider.value}")
                        
                        # Log successful usage
                        await provider_service.record_usage(
                            instance_id=str(incident_instance.id),
                            llm_model=llm_model,
                            input_tokens=1000,
                            output_tokens=500,
                            cost=provider_service.estimate_cost(llm_model, 1000, 500),
                            success=True
                        )
                        break
                    else:
                        print(f"  ✗ Provider error: {validation.get('error')}")
                        # Log failed attempt
                        await provider_service.record_usage(
                            instance_id=str(incident_instance.id),
                            llm_model=llm_model,
                            input_tokens=0,
                            output_tokens=0,
                            cost=Decimal("0"),
                            success=False,
                            error_message=validation.get("error")
                        )
                else:
                    print(f"  ✗ No API key configured")
            
            # Test automatic fallback chain
            print("\nTesting automatic fallback chain creation...")
            
            for chain_type in ["default", "long_context", "functions"]:
                print(f"\nChain type: {chain_type}")
                chain = await config_manager.create_fallback_chain(
                    incident_instance.llm_providers[0],
                    chain_type
                )
                print(f"  Generated {len(chain)} providers in chain")
                
        finally:
            await provider_service.close()
            await config_manager.close()
    
    async def test_cost_optimization_scenario(self, db, clean_test_data):
        """Test optimizing costs across multiple personas and providers"""
        print("\n=== Cost Optimization Scenario ===")
        
        provider_service = LLMProviderService(db)
        await provider_service.initialize()
        
        try:
            # Create different persona types with different cost profiles
            type_repo = PersonaTypeRepository(db)
            
            personas = []
            
            # High-value architect (needs best models)
            architect_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"chief-architect-{uuid4().hex[:8]}",
                display_name="Chief Architect",
                category=PersonaCategory.ARCHITECTURE,
                description="High-value architectural decisions",
                base_workflow_id="wf0"
            ))
            personas.append(("architect", architect_type, Decimal("200.00")))
            
            # Regular developers (balanced cost/quality)
            dev_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"developer-{uuid4().hex[:8]}",
                display_name="Developer",
                category=PersonaCategory.DEVELOPMENT,
                description="Regular development tasks",
                base_workflow_id="wf0"
            ))
            personas.append(("developer", dev_type, Decimal("50.00")))
            
            # QA testers (cost-sensitive)
            qa_type = await type_repo.create(PersonaTypeCreate(
                type_name=f"qa-tester-{uuid4().hex[:8]}",
                display_name="QA Tester",
                category=PersonaCategory.TESTING,
                description="Test case generation and validation",
                base_workflow_id="wf5"
            ))
            personas.append(("qa", qa_type, Decimal("25.00")))
            
            # Create instances with cost-appropriate models
            factory = PersonaInstanceFactory(db)
            service = PersonaInstanceService(db)
            instances = {}
            
            for role, persona_type, daily_limit in personas:
                # Select models based on budget
                if daily_limit >= Decimal("100.00"):
                    # High budget - use premium models
                    llm_models = [
                        LLMModel(
                            provider=LLMProvider.OPENAI,
                            model_name="gpt-4-turbo-preview",
                            temperature=0.7,
                            api_key_env_var="OPENAI_API_KEY"
                        )
                    ]
                elif daily_limit >= Decimal("50.00"):
                    # Medium budget - use mid-tier models
                    llm_models = [
                        LLMModel(
                            provider=LLMProvider.OPENAI,
                            model_name="gpt-4",
                            temperature=0.7,
                            api_key_env_var="OPENAI_API_KEY"
                        )
                    ]
                else:
                    # Low budget - use cost-effective models
                    llm_models = [
                        LLMModel(
                            provider=LLMProvider.OPENAI,
                            model_name="gpt-3.5-turbo",
                            temperature=0.7,
                            api_key_env_var="OPENAI_API_KEY"
                        )
                    ]
                
                instance = await factory.create_instance(
                    instance_name=f"TEST_{role}_{uuid4().hex[:8]}",
                    persona_type_id=persona_type.id,
                    azure_devops_org="https://dev.azure.com/test",
                    azure_devops_project="Cost-Optimization-Test",
                    custom_llm_providers=llm_models,
                    custom_spend_limits={"daily": daily_limit, "monthly": daily_limit * 20}
                )
                instances[role] = instance
                
                print(f"Created {role} with ${daily_limit}/day budget using {llm_models[0].model_name}")
            
            # Simulate a day of work with cost tracking
            print("\nSimulating daily workload...")
            
            daily_tasks = {
                "architect": [
                    (8000, 4000, "System design review"),
                    (6000, 3000, "Architecture documentation"),
                    (4000, 2000, "Technical decision making")
                ],
                "developer": [
                    (2000, 1500, "Code implementation"),
                    (1500, 1000, "Code review"),
                    (1000, 800, "Bug fixing"),
                    (1500, 1200, "Feature development")
                ],
                "qa": [
                    (1000, 500, "Test case generation"),
                    (800, 400, "Test execution"),
                    (600, 300, "Bug reporting"),
                    (500, 250, "Test planning"),
                    (400, 200, "Regression testing")
                ]
            }
            
            total_cost = Decimal("0")
            
            for role, tasks in daily_tasks.items():
                instance = instances[role]
                role_cost = Decimal("0")
                
                print(f"\n{role.title()} tasks:")
                for input_tokens, output_tokens, task_name in tasks:
                    # Calculate cost
                    cost = provider_service.estimate_cost(
                        instance.llm_providers[0],
                        input_tokens,
                        output_tokens
                    )
                    
                    # Check if within budget
                    current = await service.get_instance(instance.id)
                    if current.current_spend_daily + cost <= current.spend_limit_daily:
                        # Record usage
                        await provider_service.record_usage(
                            instance_id=str(instance.id),
                            llm_model=instance.llm_providers[0],
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost=cost,
                            success=True
                        )
                        
                        await service.record_spend(instance.id, cost, task_name)
                        role_cost += cost
                        print(f"  ✓ {task_name}: ${cost:.3f}")
                    else:
                        print(f"  ✗ {task_name}: BUDGET EXCEEDED (would cost ${cost:.3f})")
                
                total_cost += role_cost
                print(f"  Total {role} cost: ${role_cost:.2f}")
            
            print(f"\nTotal daily cost across all personas: ${total_cost:.2f}")
            
            # Get optimization recommendations
            print("\nCost optimization analysis:")
            
            for role, instance in instances.items():
                current = await service.get_instance(instance.id)
                utilization = current.spend_percentage_daily
                
                if utilization < 50:
                    print(f"  {role}: Under-utilized ({utilization:.1f}%) - "
                          "Consider upgrading to better model")
                elif utilization > 90:
                    print(f"  {role}: Near limit ({utilization:.1f}%) - "
                          "Consider increasing budget or using cheaper model")
                else:
                    print(f"  {role}: Well balanced ({utilization:.1f}%)")
            
        finally:
            await provider_service.close()