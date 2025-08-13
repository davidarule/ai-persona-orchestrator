import pytest
import asyncio
import websockets
import json
from httpx import AsyncClient
import yaml

@pytest.mark.asyncio
async def test_complete_workflow():
    """Test complete workflow from work item to completion"""
    
    async with AsyncClient(base_url="https://localhost:8000") as client:
        # Create test work item
        response = await client.post("/api/workflow/execute", json={
            "work_item_id": "TEST-001",
            "workflow_type": "feature_development",
            "assigned_agents": {
                "developer": "senior_developer_agent",
                "reviewer": "code_review_agent",
                "tester": "qa_agent"
            }
        })
        
        assert response.status_code == 200
        workflow_id = response.json()["workflow_id"]
        
        # Monitor workflow progress via WebSocket
        async with websockets.connect("wss://localhost:8085/workflow-updates") as ws:
            statuses_received = []
            
            while len(statuses_received) < 10:  # Collect first 10 status updates
                message = await ws.recv()
                status = json.loads(message)
                statuses_received.append(status)
                
                # Verify status structure
                assert "agent" in status
                assert "status" in status
                assert "timestamp" in status
        
        # Verify workflow completion
        response = await client.get(f"/api/workflow/status/{workflow_id}")
        assert response.status_code == 200
        
        final_status = response.json()
        assert final_status["status"] in ["completed", "in-progress"]

if __name__ == "__main__":
    asyncio.run(test_complete_workflow())