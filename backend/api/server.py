from fastapi import FastAPI, WebSocket, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime
import yaml
import os
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import redis
import asyncpg

app = FastAPI(title="AI Persona Orchestrator API")
security = HTTPBearer()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis for pub/sub
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=True
)

# PostgreSQL connection pool
pg_pool = None

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

@app.on_event("startup")
async def startup():
    global pg_pool
    pg_pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=5432,
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DB"),
        min_size=10,
        max_size=20
    )

@app.post("/api/workflow/execute")
async def execute_workflow(
    work_item_id: str,
    workflow_type: str,
    assigned_agents: Dict[str, str],
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Start workflow execution for a work item"""
    # Trigger Camunda process
    # Start LangGraph workflow
    # Return workflow instance ID
    pass

@app.get("/api/workflow/status/{work_item_id}")
async def get_workflow_status(work_item_id: str):
    """Get current status of a workflow"""
    async with pg_pool.acquire() as conn:
        result = await conn.fetch("""
            SELECT step_name, status, agent_id, started_at, completed_at, error_message
            FROM workflow_status
            WHERE work_item_id = $1
            ORDER BY started_at DESC
        """, work_item_id)
    
    return {"work_item_id": work_item_id, "steps": result}

@app.websocket("/workflow-updates")
async def websocket_endpoint(websocket: WebSocket):
    client_id = f"client_{datetime.now().timestamp()}"
    await manager.connect(websocket, client_id)
    
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            # Process any client requests
    except:
        await manager.disconnect(client_id)