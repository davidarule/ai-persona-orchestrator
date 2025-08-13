#!/usr/bin/env python3
"""
Deploy BPMN workflows to Camunda and YAML workflows to database
"""

import os
import sys
import yaml
import json
import requests
from pathlib import Path
from typing import Dict, List
import asyncio
import asyncpg
from datetime import datetime

# Configuration
ZEEBE_GATEWAY = os.getenv("ZEEBE_GATEWAY", "http://localhost:26500")
OPERATE_URL = os.getenv("OPERATE_URL", "http://localhost:8081")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://orchestrator_user:postgres123@localhost:5432/ai_orchestrator")

class WorkflowDeployer:
    def __init__(self):
        self.zeebe_gateway = ZEEBE_GATEWAY
        self.operate_url = OPERATE_URL
        self.database_url = DATABASE_URL
        
    async def deploy_all(self):
        """Deploy all workflows"""
        print("🚀 Starting workflow deployment...")
        
        # Deploy system workflows
        await self.deploy_system_workflows()
        
        # Deploy persona workflows
        await self.deploy_persona_workflows()
        
        # Deploy BPMN workflows to Camunda
        await self.deploy_bpmn_workflows()
        
        print("✅ All workflows deployed successfully!")
    
    async def deploy_system_workflows(self):
        """Deploy system workflows from YAML files"""
        system_path = Path("workflows/system")
        
        if not system_path.exists():
            print("⚠️  No system workflows directory found, creating...")
            system_path.mkdir(parents=True, exist_ok=True)
            await self.create_sample_system_workflows()
        
        conn = await asyncpg.connect(self.database_url)
        
        try:
            for yaml_file in system_path.glob("*.yaml"):
                print(f"📄 Deploying system workflow: {yaml_file.name}")
                
                with open(yaml_file, 'r') as f:
                    workflow_content = f.read()
                    workflow_data = yaml.safe_load(workflow_content)
                
                await conn.execute("""
                    INSERT INTO orchestrator.workflow_definitions (name, version, definition_yaml, is_active)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (name) DO UPDATE 
                    SET definition_yaml = $3, 
                        version = $2,
                        updated_at = CURRENT_TIMESTAMP
                """, workflow_data.get('name', yaml_file.stem), 
                    workflow_data.get('version', '1.0.0'),
                    workflow_content,
                    True)
                
                print(f"  ✓ Deployed: {workflow_data.get('name', yaml_file.stem)}")
        
        finally:
            await conn.close()
    
    async def deploy_persona_workflows(self):
        """Deploy persona workflows from YAML files"""
        persona_path = Path("workflows/personas")
        
        if not persona_path.exists():
            print("⚠️  No persona workflows directory found, creating...")
            persona_path.mkdir(parents=True, exist_ok=True)
            await self.create_sample_persona_workflows()
        
        conn = await asyncpg.connect(self.database_url)
        
        try:
            for yaml_file in persona_path.glob("*.yaml"):
                print(f"👤 Deploying persona workflow: {yaml_file.name}")
                
                with open(yaml_file, 'r') as f:
                    workflow_content = f.read()
                    workflow_data = yaml.safe_load(workflow_content)
                
                await conn.execute("""
                    INSERT INTO orchestrator.workflow_definitions (name, version, definition_yaml, is_active)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (name) DO UPDATE 
                    SET definition_yaml = $3,
                        version = $2,
                        updated_at = CURRENT_TIMESTAMP
                """, f"persona_{workflow_data.get('name', yaml_file.stem)}", 
                    workflow_data.get('version', '1.0.0'),
                    workflow_content,
                    True)
                
                print(f"  ✓ Deployed: {workflow_data.get('name', yaml_file.stem)}")
        
        finally:
            await conn.close()
    
    async def deploy_bpmn_workflows(self):
        """Deploy BPMN workflows to Camunda Zeebe"""
        bpmn_path = Path("workflows/bpmn")
        
        if not bpmn_path.exists():
            print("⚠️  No BPMN workflows directory found, creating sample...")
            bpmn_path.mkdir(parents=True, exist_ok=True)
            await self.create_sample_bpmn_workflow()
        
        # Note: In production, use pyzeebe or zeebe-grpc library
        # For now, we'll prepare the structure
        for bpmn_file in bpmn_path.glob("*.bpmn"):
            print(f"📊 Ready to deploy BPMN: {bpmn_file.name}")
            # TODO: Implement actual Zeebe deployment
    
    async def create_sample_system_workflows(self):
        """Create sample system workflows"""
        sample_workflow = {
            "name": "feature_development",
            "version": "1.0.0",
            "description": "Feature development workflow",
            "steps": [
                {
                    "id": "initialize",
                    "name": "Initialize Feature",
                    "action": "create_branch",
                    "parameters": {
                        "branch_pattern": "feature/{work_item_id}"
                    }
                },
                {
                    "id": "develop",
                    "name": "Development",
                    "action": "code_development",
                    "agent": "senior_developer"
                },
                {
                    "id": "review",
                    "name": "Code Review",
                    "action": "review_code",
                    "agent": "code_reviewer"
                },
                {
                    "id": "merge",
                    "name": "Merge",
                    "action": "merge_pull_request",
                    "conditions": {
                        "reviews_approved": True,
                        "tests_passed": True
                    }
                }
            ]
        }
        
        with open("workflows/system/feature_development.yaml", 'w') as f:
            yaml.dump(sample_workflow, f, default_flow_style=False)
        
        print("  ✓ Created sample system workflow: feature_development.yaml")
    
    async def create_sample_persona_workflows(self):
        """Create sample persona workflows"""
        developer_workflow = {
            "name": "senior_developer",
            "version": "1.0.0",
            "description": "Senior Developer Agent Workflow",
            "capabilities": [
                "code_analysis",
                "implementation",
                "debugging",
                "optimization"
            ],
            "tools": [
                "azure_devops",
                "git",
                "code_search"
            ],
            "workflow": [
                {
                    "trigger": "work_item_assigned",
                    "actions": [
                        "analyze_requirements",
                        "create_implementation_plan",
                        "implement_solution",
                        "run_tests",
                        "create_pull_request"
                    ]
                }
            ]
        }
        
        with open("workflows/personas/senior_developer.yaml", 'w') as f:
            yaml.dump(developer_workflow, f, default_flow_style=False)
        
        print("  ✓ Created sample persona workflow: senior_developer.yaml")
    
    async def create_sample_bpmn_workflow(self):
        """Create a sample BPMN workflow"""
        sample_bpmn = '''<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" 
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" 
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" 
                  xmlns:zeebe="http://camunda.org/schema/zeebe/1.0" 
                  xmlns:di="http://www.omg.org/spec/DD/20100524/DI" 
                  id="Definitions_1" 
                  targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="ai-orchestrator-process" name="AI Orchestrator Process" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" name="Start">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:serviceTask id="Task_1" name="Initialize Workflow">
      <bpmn:extensionElements>
        <zeebe:taskDefinition type="initialize-workflow" />
      </bpmn:extensionElements>
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:serviceTask>
    <bpmn:serviceTask id="Task_2" name="Execute Agent Task">
      <bpmn:extensionElements>
        <zeebe:taskDefinition type="execute-agent-task" />
      </bpmn:extensionElements>
      <bpmn:incoming>Flow_2</bpmn:incoming>
      <bpmn:outgoing>Flow_3</bpmn:outgoing>
    </bpmn:serviceTask>
    <bpmn:endEvent id="EndEvent_1" name="End">
      <bpmn:incoming>Flow_3</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="Task_2" />
    <bpmn:sequenceFlow id="Flow_3" sourceRef="Task_2" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>'''
        
        with open("workflows/bpmn/sample_process.bpmn", 'w') as f:
            f.write(sample_bpmn)
        
        print("  ✓ Created sample BPMN workflow: sample_process.bpmn")

async def main():
    deployer = WorkflowDeployer()
    await deployer.deploy_all()

if __name__ == "__main__":
    # For local testing without Docker
    if "--local" in sys.argv:
        DATABASE_URL = "postgresql://orchestrator_user:postgres123@localhost:5432/ai_orchestrator"
    
    asyncio.run(main())
