"""
Unit tests for PersonaInstance model and repository
"""

import pytest
from uuid import uuid4, UUID
import uuid
from datetime import datetime
from decimal import Decimal

from backend.models.persona_instance import (
    PersonaInstance,
    PersonaInstanceCreate,
    PersonaInstanceUpdate,
    PersonaInstanceResponse,
    LLMProvider,
    LLMModel
)
from backend.repositories.persona_instance_repository import PersonaInstanceRepository
from backend.services.persona_instance_service import PersonaInstanceService


class TestPersonaInstanceModel:
    """Test PersonaInstance data models"""
    
    def test_llm_model_creation(self):
        """Test creating an LLMModel"""
        llm = LLMModel(
            provider=LLMProvider.OPENAI,
            model_name="gpt-4-turbo-preview",
            temperature=0.7,
            max_tokens=4096,
            api_key_env_var="OPENAI_API_KEY"
        )
        
        assert llm.provider == LLMProvider.OPENAI
        assert llm.model_name == "gpt-4-turbo-preview"
        assert llm.temperature == 0.7
        assert llm.max_tokens == 4096
    
    def test_persona_instance_creation(self):
        """Test creating a PersonaInstance"""
        instance = PersonaInstance(
            id=uuid4(),
            instance_name="Test Bot - Project Alpha",
            persona_type_id=UUID(str(uuid4())),
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="Project Alpha",
            repository_name="test-repo",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ],
            spend_limit_daily=Decimal("50.00"),
            spend_limit_monthly=Decimal("1000.00"),
            max_concurrent_tasks=5,
            priority_level=1,
            custom_settings={"test": "value"},
            is_active=True,
            created_at=datetime.now()
        )
        
        assert instance.instance_name == "Test Bot - Project Alpha"
        assert instance.azure_devops_project == "Project Alpha"
        assert len(instance.llm_providers) == 1
        assert instance.spend_limit_daily == Decimal("50.00")
        assert instance.max_concurrent_tasks == 5
    
    def test_instance_name_validation(self):
        """Test instance name validation"""
        with pytest.raises(ValueError, match="Instance name cannot be empty"):
            PersonaInstanceCreate(
                instance_name="",
                persona_type_id=UUID(str(uuid4())),
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="Test",
                llm_providers=[
                    LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name="gpt-4",
                        api_key_env_var="OPENAI_API_KEY"
                    )
                ]
            )
    
    def test_azure_devops_org_normalization(self):
        """Test Azure DevOps org URL normalization"""
        instance = PersonaInstanceCreate(
            instance_name="Test Bot",
            persona_type_id=UUID(str(uuid4())),
            azure_devops_org="dev.azure.com/test",  # Missing https://
            azure_devops_project="Test",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.ANTHROPIC,
                    model_name="claude-3",
                    api_key_env_var="ANTHROPIC_API_KEY"
                )
            ]
        )
        
        assert instance.azure_devops_org == "https://dev.azure.com/test"
    
    def test_spend_limit_validation(self):
        """Test spend limit validation"""
        with pytest.raises(ValueError, match="Daily spend limit seems too high"):
            PersonaInstanceCreate(
                instance_name="Test Bot",
                persona_type_id=UUID(str(uuid4())),
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="Test",
                llm_providers=[
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )
        ],
                spend_limit_daily=Decimal("1500.00")  # Over $1000
            )
    
    def test_persona_instance_response(self):
        """Test PersonaInstanceResponse calculations"""
        response = PersonaInstanceResponse(
            id=uuid4(),
            instance_name="Test Bot",
            persona_type_id=UUID(str(uuid4())),
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="Test",
            llm_providers=[
            LLMModel(
                provider=LLMProvider.OPENAI,
                model_name="gpt-4",
                api_key_env_var="OPENAI_API_KEY"
            )
        ],
            spend_limit_daily=Decimal("100.00"),
            spend_limit_monthly=Decimal("2000.00"),
            current_spend_daily=Decimal("25.00"),
            current_spend_monthly=Decimal("500.00"),
            max_concurrent_tasks=10,
            current_task_count=3
        )
        
        response.calculate_spend_percentages()
        response.calculate_capacity()
        
        assert response.spend_percentage_daily == 25.0
        assert response.spend_percentage_monthly == 25.0
        assert response.available_capacity == 7


@pytest.mark.asyncio
class TestPersonaInstanceRepository:
    """Test PersonaInstanceRepository database operations"""
    
    async def test_create_persona_instance(self, db, test_persona_type_id, clean_test_data):
        """Test creating a persona instance"""
        repo = PersonaInstanceRepository(db)
        
        import uuid
        unique_suffix = uuid.uuid4().hex[:8]
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Developer_Bot_{unique_suffix}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="TestProject",
            repository_name="test-repo",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    temperature=0.7,
                    api_key_env_var="OPENAI_API_KEY"
                )
            ],
            spend_limit_daily=Decimal("50.00"),
            spend_limit_monthly=Decimal("1000.00"),
            max_concurrent_tasks=5,
            priority_level=1,
            custom_settings={"key": "value"}
        )
        
        instance = await repo.create(create_data)
        
        assert instance is not None
        assert instance.id is not None
        assert instance.instance_name.startswith("TEST_Developer_Bot_")
        assert instance.azure_devops_project == "TestProject"
        assert len(instance.llm_providers) == 1
        assert instance.llm_providers[0].provider == LLMProvider.OPENAI
        assert instance.spend_limit_daily == Decimal("50.00")
    
    async def test_get_instance_by_id(self, db, test_persona_type_id, clean_test_data):
        """Test retrieving instance by ID"""
        repo = PersonaInstanceRepository(db)
        
        # Create instance
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Get_By_ID_{uuid.uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="TestProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.GEMINI,
                    model_name="gemini-pro",
                    api_key_env_var="GEMINI_API_KEY"
                )
            ]
        )
        created = await repo.create(create_data)
        
        # Retrieve it
        retrieved = await repo.get_by_id(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.instance_name.startswith("TEST_Get_By_ID_")
        assert retrieved.persona_type_name is not None  # From join
    
    async def test_get_instance_by_name_and_project(self, db, test_persona_type_id, clean_test_data):
        """Test retrieving instance by name and project"""
        repo = PersonaInstanceRepository(db)
        
        # Create instance
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Unique_Instance_{uuid.uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="UniqueProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.ANTHROPIC,
                    model_name="claude-3",
                    api_key_env_var="ANTHROPIC_API_KEY"
                )
            ]
        )
        await repo.create(create_data)
        
        # Retrieve it
        retrieved = await repo.get_by_name_and_project(
            create_data.instance_name,
            "UniqueProject"
        )
        
        assert retrieved is not None
        assert retrieved.instance_name.startswith("TEST_Unique_Instance_")
        assert retrieved.azure_devops_project == "UniqueProject"
    
    async def test_list_instances(self, db, test_persona_type_id, clean_test_data):
        """Test listing instances with filters"""
        repo = PersonaInstanceRepository(db)
        
        # Create multiple instances
        for i in range(3):
            await repo.create(PersonaInstanceCreate(
                instance_name=f"TEST_List_Test_{i}_{uuid.uuid4().hex[:8]}",
                persona_type_id=test_persona_type_id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project="ListProject",
                llm_providers=[
                    LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name="gpt-3.5-turbo",
                        api_key_env_var="OPENAI_API_KEY"
                    )
                ],
                is_active=i % 2 == 0  # 0 and 2 are active
            ))
        
        # List all in project
        all_instances = await repo.list_all(project="ListProject")
        assert len(all_instances) >= 3
        
        # List only active
        active_instances = await repo.list_all(
            project="ListProject",
            is_active=True
        )
        assert len(active_instances) >= 2
    
    async def test_update_instance(self, db, test_persona_type_id, clean_test_data):
        """Test updating an instance"""
        repo = PersonaInstanceRepository(db)
        
        # Create instance
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Update_{uuid.uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="UpdateProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ],
            max_concurrent_tasks=5
        )
        created = await repo.create(create_data)
        
        # Update it
        update_data = PersonaInstanceUpdate(
            instance_name=f"TEST_Updated_{uuid.uuid4().hex[:8]}",
            max_concurrent_tasks=10,
            custom_settings={"updated": True}
        )
        updated = await repo.update(created.id, update_data)
        
        assert updated is not None
        assert updated.instance_name.startswith("TEST_Updated_")
        assert updated.max_concurrent_tasks == 10
        assert updated.custom_settings["updated"] is True
    
    async def test_update_spend(self, db, test_persona_type_id, clean_test_data):
        """Test updating spend amounts"""
        repo = PersonaInstanceRepository(db)
        
        # Create instance
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Spend_{uuid.uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="SpendProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ]
        )
        created = await repo.create(create_data)
        
        # Update spend
        success = await repo.update_spend(
            created.id,
            Decimal("10.50"),
            Decimal("10.50")
        )
        assert success is True
        
        # Check updated values
        updated = await repo.get_by_id(created.id)
        assert updated.current_spend_daily == Decimal("10.50")
        assert updated.current_spend_monthly == Decimal("10.50")
    
    async def test_check_spend_limits(self, db, test_persona_type_id, clean_test_data):
        """Test checking spend limits"""
        repo = PersonaInstanceRepository(db)
        
        # Create instance with low limits
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Limit_{uuid.uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="LimitProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ],
            spend_limit_daily=Decimal("10.00"),
            spend_limit_monthly=Decimal("100.00")
        )
        created = await repo.create(create_data)
        
        # Update spend to exceed daily limit
        await repo.update_spend(
            created.id,
            Decimal("15.00"),
            Decimal("15.00")
        )
        
        # Check limits
        limits = await repo.check_spend_limits(created.id)
        assert limits["daily_exceeded"] is True
        assert limits["monthly_exceeded"] is False
    
    async def test_deactivate_instance(self, db, test_persona_type_id, clean_test_data):
        """Test deactivating an instance"""
        repo = PersonaInstanceRepository(db)
        
        # Create instance
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Deactivate_{uuid.uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="DeactivateProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ]
        )
        created = await repo.create(create_data)
        
        # Deactivate
        success = await repo.deactivate(created.id)
        assert success is True
        
        # Check it's inactive
        instance = await repo.get_by_id(created.id)
        assert instance.is_active is False


@pytest.mark.asyncio
class TestPersonaInstanceService:
    """Test PersonaInstanceService business logic"""
    
    async def test_create_instance_validates_duplicates(self, db, test_persona_type_id, clean_test_data):
        """Test that service prevents duplicate instances"""
        service = PersonaInstanceService(db)
        
        # Create first instance
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Duplicate_{uuid.uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="DuplicateProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ]
        )
        await service.create_instance(create_data)
        
        # Try to create duplicate
        with pytest.raises(ValueError, match="already exists in project"):
            await service.create_instance(create_data)
    
    async def test_create_instance_validates_persona_type(self, db):
        """Test that service validates persona type exists"""
        service = PersonaInstanceService(db)
        
        # Try with non-existent persona type
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Invalid_Type_{uuid.uuid4().hex[:8]}",
            persona_type_id=UUID(str(uuid4())),  # Random UUID
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="InvalidTypeProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ]
        )
        
        with pytest.raises(ValueError, match="does not exist"):
            await service.create_instance(create_data)
    
    async def test_find_available_instance(self, db, test_persona_type_id, clean_test_data):
        """Test finding available instance with capacity"""
        service = PersonaInstanceService(db)
        
        # Create instance
        create_data = PersonaInstanceCreate(
            instance_name=f"TEST_Available_{uuid.uuid4().hex[:8]}",
            persona_type_id=test_persona_type_id,
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="AvailableProject",
            llm_providers=[
                LLMModel(
                    provider=LLMProvider.OPENAI,
                    model_name="gpt-4",
                    api_key_env_var="OPENAI_API_KEY"
                )
            ],
            max_concurrent_tasks=5
        )
        await service.create_instance(create_data)
        
        # Find available instance
        available = await service.find_available_instance(
            test_persona_type_id,
            "AvailableProject"
        )
        
        assert available is not None
        assert available.available_capacity > 0
    
    async def test_get_instance_statistics(self, db, test_persona_type_id, clean_test_data):
        """Test getting instance statistics"""
        service = PersonaInstanceService(db)
        
        # Create some instances
        for i in range(2):
            await service.create_instance(PersonaInstanceCreate(
                instance_name=f"TEST_Stats_{i}_{uuid.uuid4().hex[:8]}",
                persona_type_id=test_persona_type_id,
                azure_devops_org="https://dev.azure.com/test",
                azure_devops_project=f"StatsProject{i}",
                llm_providers=[
                    LLMModel(
                        provider=LLMProvider.OPENAI,
                        model_name="gpt-4",
                        api_key_env_var="OPENAI_API_KEY"
                    )
                ]
            ))
        
        # Get statistics
        stats = await service.get_instance_statistics()
        
        assert stats["total_instances"] >= 2
        assert stats["active_instances"] >= 2
        assert len(stats["by_project"]) >= 2