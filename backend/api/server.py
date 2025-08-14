from fastapi import FastAPI, WebSocket, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime
import yaml
import os
from dotenv import load_dotenv
import logging
from contextlib import asynccontextmanager

# Import our database service
from ..services.database import db_manager
from ..config.database import db_config

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        # Initialize database connections
        await db_manager.initialize()
        
        # Store reference in app state for backward compatibility
        app.state.pg_pool = db_manager.pg_pool
        app.state.redis = db_manager.redis_client
        
        logger.info("Application startup complete")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    
    yield
    
    # Shutdown
    try:
        await db_manager.close()
        logger.info("Application shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

app = FastAPI(title="AI Persona Orchestrator API", lifespan=lifespan)
security = HTTPBearer()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3020", "https://localhost:3020"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
    
    async def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
    
    async def broadcast_status(self, message: dict):
        for connection in self.active_connections.values():
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.get("/")
async def root():
    return {"message": "AI Persona Orchestrator API", "status": "running"}

@app.post("/api/workflow/execute")
async def execute_workflow(
    work_item_id: str,
    workflow_type: str,
    assigned_agents: Dict[str, str]
):
    """Start workflow execution for a work item"""
    # TODO: Trigger Camunda process
    # TODO: Start LangGraph workflow
    return {"workflow_id": f"wf_{work_item_id}_{datetime.now().timestamp()}"}

@app.get("/api/workflow/status/{work_item_id}")
async def get_workflow_status(work_item_id: str):
    """Get current status of a workflow"""
    # TODO: Query from database
    return {
        "work_item_id": work_item_id, 
        "status": "in_progress",
        "steps": []
    }

@app.get("/api/workflow/structure")
async def get_workflow_structure():
    """Get workflow structure for visualization"""
    # TODO: Load from configuration
    return {
        "nodes": [
            {"id": "1", "label": "Initialize", "x": 100, "y": 100},
            {"id": "2", "label": "Development", "x": 300, "y": 100},
            {"id": "3", "label": "Review", "x": 500, "y": 100}
        ],
        "edges": [
            {"source": "1", "target": "2"},
            {"source": "2", "target": "3"}
        ]
    }

@app.websocket("/ws/workflow-updates")
async def websocket_endpoint(websocket: WebSocket):
    client_id = f"client_{datetime.now().timestamp()}"
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Process any client requests
    except:
        await manager.disconnect(client_id)

@app.get("/api/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/health/database")
async def database_health_check():
    """Comprehensive database health check"""
    try:
        # Get health status from all databases
        db_health = await db_manager.health_check()
        
        # Get connection pool status
        pool_status = db_manager.get_pool_status()
        
        # Get table counts for critical tables
        table_counts = {}
        if db_health["postgresql"]:
            try:
                critical_tables = [
                    "workflow_definitions",
                    "persona_types", 
                    "persona_instances",
                    "mcp_servers"
                ]
                
                for table in critical_tables:
                    count = await db_manager.execute_query(
                        f"SELECT COUNT(*) FROM orchestrator.{table}",
                        fetch_one=True
                    )
                    table_counts[table] = count["count"] if count else 0
            except Exception as e:
                logger.error(f"Error getting table counts: {e}")
        
        # Determine overall health
        all_healthy = all(db_health.values())
        
        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": datetime.now().isoformat(),
            "databases": db_health,
            "connection_pools": pool_status,
            "table_counts": table_counts,
            "details": {
                "postgresql_port": db_config.postgresql.port,
                "redis_url": db_config.redis.url,
                "neo4j_uri": db_config.neo4j.uri if db_config.neo4j else None
            }
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@app.get("/api/health/detailed")
async def detailed_health_check():
    """Detailed system health check including all components"""
    health_data = {
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }
    
    # API health
    health_data["components"]["api"] = {
        "status": "healthy",
        "version": "1.0.0"
    }
    
    # Database health
    try:
        db_health = await database_health_check()
        health_data["components"]["databases"] = db_health
    except:
        health_data["components"]["databases"] = {"status": "error"}
    
    # WebSocket connections
    health_data["components"]["websocket"] = {
        "status": "healthy",
        "active_connections": len(manager.active_connections)
    }
    
    # Overall status
    all_healthy = all(
        comp.get("status") == "healthy" 
        for comp in health_data["components"].values()
    )
    health_data["status"] = "healthy" if all_healthy else "degraded"
    
    return health_data
