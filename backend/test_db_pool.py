#!/usr/bin/env python3
"""
Test script for database connection pooling
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.database import db_manager
from backend.config.database import db_config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_database_connections():
    """Test database connection pooling and health checks"""
    
    print("🔍 Testing Database Connection Pooling...\n")
    
    # Initialize connections
    print("1️⃣  Initializing database connections...")
    try:
        await db_manager.initialize()
        print("✅ Database connections initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return
    
    # Test health check
    print("\n2️⃣  Testing health checks...")
    health = await db_manager.health_check()
    for db, status in health.items():
        print(f"   {db}: {'✅' if status else '❌'}")
    
    # Test PostgreSQL queries
    print("\n3️⃣  Testing PostgreSQL queries...")
    try:
        # Simple query
        result = await db_manager.execute_query("SELECT version()", fetch_one=True)
        print(f"   PostgreSQL version: {result['version'][:50]}...")
        
        # Count workflows
        count = await db_manager.execute_query(
            "SELECT COUNT(*) as count FROM orchestrator.workflow_definitions",
            fetch_one=True
        )
        print(f"   Workflow definitions: {count['count']}")
        
        # Test concurrent connections
        print("\n4️⃣  Testing concurrent connections...")
        tasks = []
        for i in range(5):
            task = db_manager.execute_query(
                "SELECT pg_sleep(0.1), $1::text as task_id",
                str(i),
                fetch_one=True
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        print(f"   Completed {len(results)} concurrent queries")
        
    except Exception as e:
        print(f"❌ PostgreSQL test failed: {e}")
    
    # Test Redis
    print("\n5️⃣  Testing Redis operations...")
    try:
        # Set a value
        await db_manager.redis_execute("set", "test:key", "test_value")
        
        # Get the value
        value = await db_manager.redis_execute("get", "test:key")
        print(f"   Redis get/set: {'✅' if value == 'test_value' else '❌'}")
        
        # Clean up
        await db_manager.redis_execute("delete", "test:key")
        
    except Exception as e:
        print(f"❌ Redis test failed: {e}")
    
    # Get pool status
    print("\n6️⃣  Connection pool status:")
    status = db_manager.get_pool_status()
    
    print(f"\n   PostgreSQL:")
    print(f"     Pool size: {status['postgresql']['min_size']}-{status['postgresql']['max_size']}")
    print(f"     Current connections: {status['postgresql']['current_size']}")
    print(f"     Total queries: {status['postgresql']['queries']}")
    print(f"     Errors: {status['postgresql']['errors']}")
    
    print(f"\n   Redis:")
    print(f"     Commands executed: {status['redis']['commands']}")
    print(f"     Errors: {status['redis']['errors']}")
    
    # Test database config
    print("\n7️⃣  Database configuration:")
    print(f"   PostgreSQL: {db_config.postgresql.host}:{db_config.postgresql.port}")
    print(f"   Pool size: {db_config.postgresql.pool_min_size}-{db_config.postgresql.pool_max_size}")
    print(f"   Redis: {db_config.redis.url}")
    
    # Close connections
    print("\n8️⃣  Closing connections...")
    await db_manager.close()
    print("✅ All connections closed")
    
    print("\n✨ Database connection pooling test complete!")


if __name__ == "__main__":
    asyncio.run(test_database_connections())