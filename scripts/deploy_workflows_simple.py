#!/usr/bin/env python3
"""
Simple workflow deployment script
"""

import os
import yaml
import psycopg2
from pathlib import Path
from datetime import datetime

# Get credentials from environment
DB_HOST = os.getenv('POSTGRES_HOST', 'localhost')
DB_PORT = os.getenv('POSTGRES_PORT', '5434')
DB_NAME = os.getenv('POSTGRES_DB', 'ai_orchestrator')
DB_USER = os.getenv('POSTGRES_USER', 'orchestrator_user')
DB_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'Drool00!425938')

def deploy_workflows():
    """Deploy all workflows to database"""
    
    # Connect to database
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cur = conn.cursor()
    
    # Deploy persona workflows
    persona_path = Path("workflows/personas")
    persona_count = 0
    
    print("🚀 Deploying persona workflows...")
    for yaml_file in persona_path.glob("*.yaml"):
        print(f"  📄 Deploying: {yaml_file.name}")
        
        try:
            with open(yaml_file, 'r') as f:
                workflow_content = f.read()
                workflow_data = yaml.safe_load(workflow_content)
            
            workflow_name = workflow_data.get('metadata', {}).get('name', yaml_file.stem)
            workflow_version = workflow_data.get('metadata', {}).get('version', '1.0.0')
        except yaml.YAMLError as e:
            print(f"    ⚠️  YAML error in {yaml_file.name}: {e}")
            continue
        except Exception as e:
            print(f"    ❌ Error processing {yaml_file.name}: {e}")
            continue
        
        cur.execute("""
            INSERT INTO orchestrator.workflow_definitions (name, version, definition_yaml, is_active)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE 
            SET definition_yaml = %s, 
                version = %s,
                updated_at = CURRENT_TIMESTAMP
        """, (workflow_name, workflow_version, workflow_content, True, workflow_content, workflow_version))
        
        persona_count += 1
    
    # Deploy system workflows
    system_path = Path("workflows/system")
    system_count = 0
    
    print("\n🚀 Deploying system workflows...")
    for yaml_file in system_path.glob("*.yaml"):
        print(f"  📄 Deploying: {yaml_file.name}")
        
        try:
            with open(yaml_file, 'r') as f:
                workflow_content = f.read()
                workflow_data = yaml.safe_load(workflow_content)
            
            workflow_name = workflow_data.get('metadata', {}).get('name', yaml_file.stem)
            workflow_version = workflow_data.get('metadata', {}).get('version', '1.0.0')
        except yaml.YAMLError as e:
            print(f"    ⚠️  YAML error in {yaml_file.name}: {e}")
            continue
        except Exception as e:
            print(f"    ❌ Error processing {yaml_file.name}: {e}")
            continue
        
        cur.execute("""
            INSERT INTO orchestrator.workflow_definitions (name, version, definition_yaml, is_active)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE 
            SET definition_yaml = %s, 
                version = %s,
                updated_at = CURRENT_TIMESTAMP
        """, (workflow_name, workflow_version, workflow_content, True, workflow_content, workflow_version))
        
        system_count += 1
    
    # Commit and close
    conn.commit()
    cur.close()
    conn.close()
    
    print(f"\n✅ Deployment complete!")
    print(f"   - {persona_count} persona workflows")
    print(f"   - {system_count} system workflows")
    print(f"   - Total: {persona_count + system_count} workflows")

if __name__ == "__main__":
    deploy_workflows()