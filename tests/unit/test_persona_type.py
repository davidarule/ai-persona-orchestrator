"""
Unit tests for PersonaType model and repository
"""

import pytest
from uuid import uuid4
from datetime import datetime

from backend.models.persona_type import (
    PersonaType,
    PersonaTypeCreate,
    PersonaTypeUpdate,
    PersonaCategory
)
from backend.repositories.persona_repository import PersonaTypeRepository
from backend.services.persona_service import PersonaTypeService


class TestPersonaTypeModel:
    """Test PersonaType data models"""
    
    def test_persona_type_creation(self):
        """Test creating a PersonaType instance"""
        persona = PersonaType(
            id=uuid4(),
            type_name="test-persona",
            display_name="Test Persona",
            category=PersonaCategory.DEVELOPMENT,
            description="A test persona",
            base_workflow_id="test-workflow",
            default_capabilities={"can_test": True},
            required_skills=["testing"],
            compatible_workflows=["wf0"],
            created_at=datetime.now()
        )
        
        assert persona.type_name == "test-persona"
        assert persona.display_name == "Test Persona"
        assert persona.category == PersonaCategory.DEVELOPMENT
        assert persona.default_capabilities["can_test"] is True
        assert "testing" in persona.required_skills
        assert "wf0" in persona.compatible_workflows
    
    def test_persona_type_create_schema(self):
        """Test PersonaTypeCreate validation"""
        create_data = PersonaTypeCreate(
            type_name="new-persona",
            display_name="New Persona",
            category=PersonaCategory.QUALITY,
            description="A new test persona"
        )
        
        assert create_data.type_name == "new-persona"
        assert create_data.category == PersonaCategory.QUALITY
        assert create_data.default_capabilities == {}
        assert create_data.required_skills == []
    
    def test_persona_type_update_schema(self):
        """Test PersonaTypeUpdate with partial data"""
        update_data = PersonaTypeUpdate(
            display_name="Updated Name",
            category=PersonaCategory.ARCHITECTURE
        )
        
        assert update_data.display_name == "Updated Name"
        assert update_data.category == PersonaCategory.ARCHITECTURE
        assert update_data.description is None
        assert update_data.base_workflow_id is None
    
    def test_persona_categories(self):
        """Test all persona categories are valid"""
        categories = [
            PersonaCategory.DEVELOPMENT,
            PersonaCategory.QUALITY,
            PersonaCategory.ARCHITECTURE,
            PersonaCategory.OPERATIONS,
            PersonaCategory.MANAGEMENT,
            PersonaCategory.SPECIALIZED
        ]
        
        for category in categories:
            persona = PersonaTypeCreate(
                type_name=f"test-{category}",
                display_name=f"Test {category}",
                category=category
            )
            assert persona.category == category


@pytest.mark.asyncio
class TestPersonaTypeRepository:
    """Test PersonaTypeRepository database operations"""
    
    async def test_create_persona_type(self, db):
        """Test creating a persona type in the database"""
        repo = PersonaTypeRepository(db)
        
        create_data = PersonaTypeCreate(
            type_name="test-developer",
            display_name="Test Developer",
            category=PersonaCategory.DEVELOPMENT,
            description="A test developer persona",
            base_workflow_id="persona-test-developer",
            default_capabilities={"can_code": True},
            required_skills=["python", "testing"],
            compatible_workflows=["wf0", "wf1"]
        )
        
        persona = await repo.create(create_data)
        
        assert persona is not None
        assert persona.id is not None
        assert persona.type_name == "test-developer"
        assert persona.display_name == "Test Developer"
        assert persona.category == PersonaCategory.DEVELOPMENT
        assert persona.default_capabilities.get("can_code") is True
        assert "python" in persona.required_skills
        assert "wf0" in persona.compatible_workflows
    
    async def test_get_persona_type_by_id(self, db):
        """Test retrieving a persona type by ID"""
        repo = PersonaTypeRepository(db)
        
        # First create a persona
        create_data = PersonaTypeCreate(
            type_name="test-architect",
            display_name="Test Architect",
            category=PersonaCategory.ARCHITECTURE
        )
        created = await repo.create(create_data)
        
        # Now retrieve it
        retrieved = await repo.get_by_id(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.type_name == "test-architect"
        assert retrieved.display_name == "Test Architect"
    
    async def test_get_persona_type_by_name(self, db):
        """Test retrieving a persona type by type_name"""
        repo = PersonaTypeRepository(db)
        
        # First create a persona
        create_data = PersonaTypeCreate(
            type_name="test-qa-engineer",
            display_name="Test QA Engineer",
            category=PersonaCategory.QUALITY
        )
        await repo.create(create_data)
        
        # Now retrieve it by name
        retrieved = await repo.get_by_type_name("test-qa-engineer")
        
        assert retrieved is not None
        assert retrieved.type_name == "test-qa-engineer"
        assert retrieved.display_name == "Test QA Engineer"
        assert retrieved.category == PersonaCategory.QUALITY
    
    async def test_list_persona_types(self, db):
        """Test listing all persona types"""
        repo = PersonaTypeRepository(db)
        
        # Create multiple personas
        personas_data = [
            PersonaTypeCreate(
                type_name="test-list-1",
                display_name="Test List 1",
                category=PersonaCategory.DEVELOPMENT
            ),
            PersonaTypeCreate(
                type_name="test-list-2",
                display_name="Test List 2",
                category=PersonaCategory.QUALITY
            ),
            PersonaTypeCreate(
                type_name="test-list-3",
                display_name="Test List 3",
                category=PersonaCategory.DEVELOPMENT
            )
        ]
        
        for data in personas_data:
            await repo.create(data)
        
        # List all
        all_personas = await repo.list_all()
        test_personas = [p for p in all_personas if p.type_name.startswith("test-list-")]
        
        assert len(test_personas) >= 3
        
        # List by category
        dev_personas = await repo.list_all(category=PersonaCategory.DEVELOPMENT)
        dev_test_personas = [p for p in dev_personas if p.type_name.startswith("test-list-")]
        
        assert len(dev_test_personas) == 2
    
    async def test_update_persona_type(self, db):
        """Test updating a persona type"""
        repo = PersonaTypeRepository(db)
        
        # Create a persona
        create_data = PersonaTypeCreate(
            type_name="test-update",
            display_name="Original Name",
            category=PersonaCategory.OPERATIONS,
            description="Original description"
        )
        created = await repo.create(create_data)
        
        # Update it
        update_data = PersonaTypeUpdate(
            display_name="Updated Name",
            description="Updated description",
            required_skills=["new_skill"]
        )
        updated = await repo.update(created.id, update_data)
        
        assert updated is not None
        assert updated.display_name == "Updated Name"
        assert updated.description == "Updated description"
        assert "new_skill" in updated.required_skills
        assert updated.category == PersonaCategory.OPERATIONS  # Unchanged
    
    async def test_delete_persona_type(self, db):
        """Test deleting a persona type"""
        repo = PersonaTypeRepository(db)
        
        # Create a persona
        create_data = PersonaTypeCreate(
            type_name="test-delete",
            display_name="To Delete",
            category=PersonaCategory.SPECIALIZED
        )
        created = await repo.create(create_data)
        
        # Delete it
        deleted = await repo.delete(created.id)
        assert deleted is True
        
        # Verify it's gone
        retrieved = await repo.get_by_id(created.id)
        assert retrieved is None
    
    async def test_bulk_create_personas(self, db):
        """Test creating multiple personas at once"""
        repo = PersonaTypeRepository(db)
        
        personas_data = [
            PersonaTypeCreate(
                type_name=f"bulk-test-{i}",
                display_name=f"Bulk Test {i}",
                category=PersonaCategory.DEVELOPMENT
            )
            for i in range(5)
        ]
        
        created = await repo.bulk_create(personas_data)
        
        assert len(created) == 5
        for i, persona in enumerate(created):
            assert persona.type_name == f"bulk-test-{i}"
            assert persona.display_name == f"Bulk Test {i}"


@pytest.mark.asyncio
class TestPersonaTypeService:
    """Test PersonaTypeService business logic"""
    
    async def test_create_persona_type_validates_workflow(self, db):
        """Test that service validates workflow exists"""
        service = PersonaTypeService(db)
        
        # Try to create with non-existent workflow
        create_data = PersonaTypeCreate(
            type_name="test-invalid-workflow",
            display_name="Test Invalid",
            category=PersonaCategory.DEVELOPMENT,
            base_workflow_id="non-existent-workflow"
        )
        
        with pytest.raises(ValueError, match="Workflow.*does not exist"):
            await service.create_persona_type(create_data)
    
    async def test_create_persona_type_prevents_duplicates(self, db):
        """Test that service prevents duplicate type_names"""
        service = PersonaTypeService(db)
        
        # Create first persona
        create_data = PersonaTypeCreate(
            type_name="test-duplicate",
            display_name="Test Duplicate",
            category=PersonaCategory.QUALITY
        )
        await service.create_persona_type(create_data)
        
        # Try to create duplicate
        with pytest.raises(ValueError, match="already exists"):
            await service.create_persona_type(create_data)
    
    async def test_get_persona_statistics(self, db):
        """Test getting statistics about persona types"""
        service = PersonaTypeService(db)
        
        # Create some test personas
        test_personas = [
            PersonaTypeCreate(
                type_name="stats-dev-1",
                display_name="Stats Dev 1",
                category=PersonaCategory.DEVELOPMENT
            ),
            PersonaTypeCreate(
                type_name="stats-dev-2",
                display_name="Stats Dev 2",
                category=PersonaCategory.DEVELOPMENT
            ),
            PersonaTypeCreate(
                type_name="stats-qa-1",
                display_name="Stats QA 1",
                category=PersonaCategory.QUALITY
            )
        ]
        
        for persona_data in test_personas:
            await service.create_persona_type(persona_data)
        
        # Get statistics
        stats = await service.get_persona_type_statistics()
        
        assert stats["total_types"] >= 3
        assert PersonaCategory.DEVELOPMENT in stats["by_category"]
        assert PersonaCategory.QUALITY in stats["by_category"]
        assert stats["by_category"][PersonaCategory.DEVELOPMENT] >= 2
        assert stats["by_category"][PersonaCategory.QUALITY] >= 1
    
    async def test_initialize_default_personas(self, db):
        """Test initializing all 25 default personas"""
        service = PersonaTypeService(db)
        
        # Initialize defaults
        defaults = await service.initialize_default_persona_types()
        
        # Should have created 25 personas
        assert len(defaults) == 25
        
        # Verify some specific ones exist
        type_names = [p.type_name for p in defaults]
        assert "software-architect" in type_names
        assert "senior-developer" in type_names
        assert "qa-test-engineer" in type_names
        assert "devsecops-engineer" in type_names
        assert "product-owner" in type_names
        assert "technical-writer" in type_names
        
        # Verify categories are distributed correctly
        by_category = {}
        for persona in defaults:
            cat = persona.category
            by_category[cat] = by_category.get(cat, 0) + 1
        
        assert by_category[PersonaCategory.DEVELOPMENT] == 5
        assert by_category[PersonaCategory.QUALITY] == 4
        assert by_category[PersonaCategory.ARCHITECTURE] == 4
        assert by_category[PersonaCategory.OPERATIONS] == 4
        assert by_category[PersonaCategory.MANAGEMENT] == 5
        assert by_category[PersonaCategory.SPECIALIZED] == 3