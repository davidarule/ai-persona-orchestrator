"""
Unit tests for Persona Instance API endpoints
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.api.server import app
from backend.models.persona_instance import (
    PersonaInstance,
    PersonaInstanceCreate,
    PersonaInstanceUpdate,
    PersonaInstanceResponse,
    LLMProvider,
    LLMModel
)
from backend.services.persona_instance_service import PersonaInstanceService
from backend.services.spend_tracking_service import SpendTrackingService
from backend.factories.persona_instance_factory import PersonaInstanceFactory


class TestPersonaInstanceAPI:
    """Test persona instance API endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_db(self):
        """Mock database manager"""
        db = AsyncMock()
        db.initialize = AsyncMock()
        db.close = AsyncMock()
        return db
    
    @pytest.fixture
    def sample_instance(self):
        """Sample persona instance"""
        return PersonaInstance(
            id=uuid4(),
            instance_name="Test Bot - Project Alpha",
            persona_type_id=uuid4(),
            azure_devops_org="https://dev.azure.com/test",
            azure_devops_project="Project Alpha",
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
            current_spend_daily=Decimal("10.00"),
            current_spend_monthly=Decimal("200.00"),
            max_concurrent_tasks=5,
            priority_level=0,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceService')
    async def test_create_persona_instance(self, mock_service_class, mock_get_db, client, mock_db, sample_instance):
        """Test creating a new persona instance"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.create_instance.return_value = sample_instance
        
        # Create request data
        create_data = {
            "instance_name": "Test Bot - Project Alpha",
            "persona_type_id": str(uuid4()),
            "azure_devops_org": "https://dev.azure.com/test",
            "azure_devops_project": "Project Alpha",
            "llm_providers": [
                {
                    "provider": "openai",
                    "model_name": "gpt-4",
                    "temperature": 0.7,
                    "api_key_env_var": "OPENAI_API_KEY"
                }
            ],
            "spend_limit_daily": "50.00",
            "spend_limit_monthly": "1000.00"
        }
        
        # Make request
        response = client.post("/api/v1/persona-instances/", json=create_data)
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["instance_name"] == "Test Bot - Project Alpha"
        assert "id" in data
        assert "llm_providers" in data
        assert len(data["llm_providers"]) == 1
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceService')
    async def test_list_persona_instances(self, mock_service_class, mock_get_db, client, mock_db, sample_instance):
        """Test listing persona instances with pagination"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        # Create multiple instances
        instances = [sample_instance for _ in range(25)]
        mock_service.list_instances.return_value = instances
        
        # Test pagination
        response = client.get("/api/v1/persona-instances/?page=1&page_size=10")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total_pages"] == 3
        assert len(data["instances"]) == 10
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceService')
    async def test_get_persona_instance(self, mock_service_class, mock_get_db, client, mock_db, sample_instance):
        """Test getting a specific persona instance"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.get_instance.return_value = sample_instance
        
        # Make request
        response = client.get(f"/api/v1/persona-instances/{sample_instance.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_instance.id)
        assert data["instance_name"] == sample_instance.instance_name
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceService')
    async def test_update_persona_instance(self, mock_service_class, mock_get_db, client, mock_db, sample_instance):
        """Test updating a persona instance"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        # Update the instance
        updated_instance = sample_instance.copy()
        updated_instance.instance_name = "Updated Bot Name"
        mock_service.update_instance.return_value = updated_instance
        
        # Make request
        update_data = {"instance_name": "Updated Bot Name"}
        response = client.patch(
            f"/api/v1/persona-instances/{sample_instance.id}",
            json=update_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["instance_name"] == "Updated Bot Name"
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceService')
    async def test_delete_persona_instance(self, mock_service_class, mock_get_db, client, mock_db):
        """Test deleting a persona instance"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.delete_instance.return_value = True
        
        # Make request
        instance_id = uuid4()
        response = client.delete(f"/api/v1/persona-instances/{instance_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Instance deleted successfully"
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceService')
    async def test_activate_deactivate_instance(self, mock_service_class, mock_get_db, client, mock_db, sample_instance):
        """Test activating and deactivating instances"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        # Test activation
        activated = sample_instance.copy()
        activated.is_active = True
        mock_service.activate_instance.return_value = activated
        
        response = client.post(f"/api/v1/persona-instances/{sample_instance.id}/activate")
        assert response.status_code == 200
        assert response.json()["is_active"] is True
        
        # Test deactivation
        deactivated = sample_instance.copy()
        deactivated.is_active = False
        mock_service.deactivate_instance.return_value = deactivated
        
        response = client.post(f"/api/v1/persona-instances/{sample_instance.id}/deactivate")
        assert response.status_code == 200
        assert response.json()["is_active"] is False
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.SpendTrackingService')
    async def test_get_spend_status(self, mock_spend_service_class, mock_get_db, client, mock_db):
        """Test getting spend status for an instance"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_spend_service = AsyncMock()
        mock_spend_service_class.return_value = mock_spend_service
        mock_spend_service.initialize = AsyncMock()
        mock_spend_service.close = AsyncMock()
        
        mock_spend_service.get_spend_status.return_value = {
            "daily_spent": Decimal("25.00"),
            "daily_limit": Decimal("50.00"),
            "daily_remaining": Decimal("25.00"),
            "daily_percentage": 50.0,
            "monthly_spent": Decimal("500.00"),
            "monthly_limit": Decimal("1000.00"),
            "monthly_remaining": Decimal("500.00"),
            "monthly_percentage": 50.0,
            "daily_exceeded": False,
            "monthly_exceeded": False
        }
        
        # Make request
        instance_id = uuid4()
        response = client.get(f"/api/v1/persona-instances/{instance_id}/spend/status")
        
        assert response.status_code == 200
        data = response.json()
        assert float(data["daily_spent"]) == 25.00
        assert data["daily_percentage"] == 50.0
        assert data["daily_exceeded"] is False
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.SpendTrackingService')
    async def test_get_spend_history(self, mock_spend_service_class, mock_get_db, client, mock_db):
        """Test getting spend history"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_spend_service = AsyncMock()
        mock_spend_service_class.return_value = mock_spend_service
        mock_spend_service.initialize = AsyncMock()
        mock_spend_service.close = AsyncMock()
        
        mock_spend_service.get_spend_history.return_value = [
            {
                "amount": Decimal("10.00"),
                "category": "llm_usage",
                "description": "GPT-4 API call",
                "created_at": datetime.utcnow()
            }
        ]
        
        # Make request
        instance_id = uuid4()
        response = client.get(f"/api/v1/persona-instances/{instance_id}/spend/history")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) == 1
        assert float(data["total_spend"]) == 10.00
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceFactory')
    async def test_create_team(self, mock_factory_class, mock_get_db, client, mock_db, sample_instance):
        """Test creating a development team"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_factory = AsyncMock()
        mock_factory_class.return_value = mock_factory
        
        # Create team instances
        team = {
            "architect": sample_instance,
            "lead_developer": sample_instance,
            "qa_engineer": sample_instance
        }
        mock_factory.create_standard_development_team.return_value = team
        
        # Make request
        team_data = {
            "project_name": "New Project",
            "azure_devops_org": "https://dev.azure.com/test",
            "azure_devops_project": "New Project",
            "team_size": "medium"
        }
        
        response = client.post("/api/v1/persona-instances/factory/team", json=team_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "architect" in data
        assert "lead_developer" in data
        assert "qa_engineer" in data
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceFactory')
    async def test_clone_instance(self, mock_factory_class, mock_get_db, client, mock_db, sample_instance):
        """Test cloning an instance"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_factory = AsyncMock()
        mock_factory_class.return_value = mock_factory
        
        cloned = sample_instance.copy()
        cloned.id = uuid4()
        cloned.instance_name = "Cloned Bot"
        mock_factory.clone_instance.return_value = cloned
        
        # Make request
        clone_data = {
            "new_instance_name": "Cloned Bot",
            "new_project": "New Project"
        }
        
        response = client.post(
            f"/api/v1/persona-instances/{sample_instance.id}/clone",
            json=clone_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["instance_name"] == "Cloned Bot"
        assert data["id"] != str(sample_instance.id)
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.SpendTrackingService')
    @patch('backend.api.routes.persona_instances.PersonaInstanceService')
    async def test_get_analytics(self, mock_service_class, mock_spend_service_class, mock_get_db, client, mock_db):
        """Test getting analytics summary"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        
        mock_spend_service = AsyncMock()
        mock_spend_service_class.return_value = mock_spend_service
        mock_spend_service.initialize = AsyncMock()
        mock_spend_service.close = AsyncMock()
        mock_spend_service.get_spend_analytics.return_value = {
            "summary": {"instance_count": 10},
            "by_category": [],
            "top_spenders": []
        }
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.get_instance_statistics.return_value = {
            "total_instances": 10,
            "active_instances": 8,
            "inactive_instances": 2
        }
        
        # Make request
        response = client.get("/api/v1/persona-instances/analytics/summary")
        
        assert response.status_code == 200
        data = response.json()
        assert "instance_stats" in data
        assert "spend_analytics" in data
        assert data["instance_stats"]["total_instances"] == 10
    
    @patch('backend.api.routes.persona_instances.get_db')
    @patch('backend.api.routes.persona_instances.PersonaInstanceService')
    async def test_reset_daily_spend(self, mock_service_class, mock_get_db, client, mock_db):
        """Test resetting daily spend"""
        # Setup mocks
        mock_get_db.return_value = mock_db
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        mock_service.reset_daily_spend_all.return_value = 15
        
        # Make request
        response = client.post("/api/v1/persona-instances/maintenance/reset-daily-spend")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Daily spend reset successfully"
        assert data["instances_affected"] == 15
    
    async def test_validation_errors(self, client):
        """Test various validation error scenarios"""
        # Test invalid instance name
        create_data = {
            "instance_name": "",  # Empty name
            "persona_type_id": str(uuid4()),
            "azure_devops_org": "https://dev.azure.com/test",
            "azure_devops_project": "Project",
            "llm_providers": [{
                "provider": "openai",
                "model_name": "gpt-4",
                "api_key_env_var": "OPENAI_API_KEY"
            }]
        }
        
        response = client.post("/api/v1/persona-instances/", json=create_data)
        assert response.status_code == 422  # Validation error
        
        # Test invalid spend limit
        create_data["instance_name"] = "Valid Name"
        create_data["spend_limit_daily"] = "2000.00"  # Over limit
        
        response = client.post("/api/v1/persona-instances/", json=create_data)
        assert response.status_code == 422
        
        # Test missing LLM providers
        create_data["spend_limit_daily"] = "50.00"
        create_data["llm_providers"] = []  # Empty list
        
        response = client.post("/api/v1/persona-instances/", json=create_data)
        assert response.status_code == 422