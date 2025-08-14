"""
Global pytest configuration and fixtures for AI Persona Orchestrator tests
"""

import pytest
import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.database import db_manager
from backend.config.database import db_config

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
async def db():
    """Initialize database connections for testing"""
    # Create new instance for each test to avoid loop issues
    from backend.services.database import DatabaseManager
    
    test_db_manager = DatabaseManager()
    await test_db_manager.initialize()
    yield test_db_manager
    await test_db_manager.close()


@pytest.fixture
async def pg_conn(db):
    """Get a PostgreSQL connection"""
    async with db.acquire_pg_connection() as conn:
        yield conn


@pytest.fixture
def redis_client(db):
    """Get Redis client"""
    return db.redis_client


@pytest.fixture
def test_personas():
    """Test personas from Azure DevOps sandbox"""
    return {
        "steve_bot": {
            "username": "steve.bot",
            "email": "steve.bot@insitec.com.au",
            "first_name": "Steve",
            "last_name": "Bot",
            "role": "System Architect",
            "persona_type": "systems-architect"
        },
        "jordan_bot": {
            "username": "jordan.bot",
            "email": "jordan.bot@insitec.com.au",
            "first_name": "Jordan",
            "last_name": "Bot",
            "role": "Backend Developer",
            "persona_type": "backend-developer"
        },
        "matt_bot": {
            "username": "matt.bot",
            "email": "matt.bot@insitec.com.au",
            "first_name": "Matt",
            "last_name": "Bot",
            "role": "Frontend Developer",
            "persona_type": "frontend-developer"
        },
        "kav_bot": {
            "username": "kav.bot",
            "email": "kav.bot@insitec.com.au",
            "first_name": "Kav",
            "last_name": "Bot",
            "role": "Test Engineer",
            "persona_type": "test-engineer"
        },
        "dave_bot": {
            "username": "dave.bot",
            "email": "dave.bot@insitec.com.au",
            "first_name": "Dave",
            "last_name": "Bot",
            "role": "Security Engineer",
            "persona_type": "security-engineer"
        },
        "lachlan_bot": {
            "username": "lachlan.bot",
            "email": "lachlan.bot@insitec.com.au",
            "first_name": "Lachlan",
            "last_name": "Bot",
            "role": "DevSecOps Engineer",
            "persona_type": "devsecops-engineer"
        },
        "shaun_bot": {
            "username": "shaun.bot",
            "email": "shaun.bot@insitec.com.au",
            "first_name": "Shaun",
            "last_name": "Bot",
            "role": "UI/UX Designer",
            "persona_type": "ui-ux-designer"
        },
        "laureen_bot": {
            "username": "laureen.bot",
            "email": "laureen.bot@insitec.com.au",
            "first_name": "Laureen",
            "last_name": "Bot",
            "role": "Technical Writer",
            "persona_type": "technical-writer"
        },
        "ruley_bot": {
            "username": "ruley.bot",
            "email": "ruley.bot@insitec.com.au",
            "first_name": "Ruley",
            "last_name": "Bot",
            "role": "Requirements Analyst",
            "persona_type": "requirements-analyst"
        },
        "brumbie_bot": {
            "username": "brumbie.bot",
            "email": "brumbie.bot@insitec.com.au",
            "first_name": "Brumbie",
            "last_name": "Bot",
            "role": "Project Manager",
            "persona_type": "product-owner"
        },
        "moby_bot": {
            "username": "moby.bot",
            "email": "moby.bot@insitec.com.au",
            "first_name": "Moby",
            "last_name": "Bot",
            "role": "Mobile Developer",
            "persona_type": "mobile-developer"
        },
        "claude_bot": {
            "username": "claude.bot",
            "email": "claude.bot@insitec.com.au",
            "first_name": "Claude",
            "last_name": "Bot",
            "role": "AI Integration",
            "persona_type": "ai-engineer"
        },
        "puck_bot": {
            "username": "puck.bot",
            "email": "puck.bot@insitec.com.au",
            "first_name": "Puck",
            "last_name": "Bot",
            "role": "Developer",
            "persona_type": "developer-engineer"
        }
    }


@pytest.fixture
def azure_devops_config():
    """Azure DevOps test configuration"""
    return {
        "org_url": os.getenv("AZURE_DEVOPS_ORG_URL", "https://dev.azure.com/data6"),
        "pat": os.getenv("AZURE_DEVOPS_PAT"),
        "test_project": "AI-Personas-Test-Sandbox-2"
    }


@pytest.fixture
async def clean_test_data(pg_conn):
    """Clean up test data after each test"""
    yield
    # Clean up any test data created
    await pg_conn.execute("""
        DELETE FROM orchestrator.persona_instances 
        WHERE instance_name LIKE 'TEST_%'
    """)
    await pg_conn.execute("""
        DELETE FROM orchestrator.workflow_executions 
        WHERE work_item_id LIKE 'TEST_%'
    """)


# Markers for different test types
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as an end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )