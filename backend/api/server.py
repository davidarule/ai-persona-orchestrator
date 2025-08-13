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
import redis.asyncio as redis
import asyncpg
from contextlib import asynccontextmanager

load_dotenv()

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.pg_pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=5432,
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DB"),
        min_size=10,
        max_size=20
    )
    app.state.redis = await redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379"),
        decode_responses=True
    )
    yield
    # Shutdown
    await app.state.pg_pool.close()
    await app.state.redis.close()

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
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
