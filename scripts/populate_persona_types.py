#!/usr/bin/env python3
"""
Populate persona_types table with all 25 persona types
"""

import psycopg2
import yaml
import json
from pathlib import Path

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    port='5434',
    database='ai_orchestrator',
    user='orchestrator_user',
    password='Drool00!425938'
)
cur = conn.cursor()

# Clear existing persona types (except the test one we created)
cur.execute("DELETE FROM orchestrator.persona_types WHERE type_name != 'software-architect'")

# Define all 25 persona types
persona_types = [
    ('ai-engineer', 'AI Engineer', 'persona-ai-engineer-workflow'),
    ('backend-developer', 'Backend Developer', 'persona-backend-developer-workflow'),
    ('business-analyst', 'Business Analyst', 'persona-business-analyst-workflow'),
    ('cloud-engineer', 'Cloud Engineer', 'persona-cloud-engineer-workflow'),
    ('configuration-release-engineer', 'Configuration Release Engineer', 'persona-configuration-release-engineer-workflow'),
    ('data-engineer-dba', 'Data Engineer/DBA', 'persona-data-engineer-dba-workflow'),
    ('developer-engineer', 'Developer/Engineer', 'persona-developer-engineer-workflow'),
    ('devsecops-engineer', 'DevSecOps Engineer', 'persona-devsecops-engineer-workflow'),
    ('engineering-manager', 'Engineering Manager', 'persona-engineering-manager-workflow'),
    ('frontend-developer', 'Frontend Developer', 'persona-frontend-developer-workflow'),
    ('integration-engineer', 'Integration Engineer', 'persona-integration-engineer-workflow'),
    ('mobile-developer', 'Mobile Developer', 'persona-mobile-developer-workflow'),
    ('product-owner', 'Product Owner', 'persona-product-owner-workflow'),
    ('qa-test-engineer', 'QA Test Engineer', 'persona-qa-test-engineer-workflow'),
    ('requirements-analyst', 'Requirements Analyst', 'persona-requirements-analyst-workflow'),
    ('scrum-master', 'Scrum Master', 'persona-scrum-master-workflow'),
    ('security-architect', 'Security Architect', 'persona-security-architect-workflow'),
    ('security-engineer', 'Security Engineer', 'persona-security-engineer-workflow'),
    ('site-reliability-engineer', 'Site Reliability Engineer', 'persona-site-reliability-engineer-workflow'),
    ('software-architect', 'Software Architect', 'persona-software-architect-workflow'),
    ('software-qa', 'Software QA', 'persona-software-qa-workflow'),
    ('systems-architect', 'Systems Architect', 'persona-systems-architect-workflow'),
    ('technical-writer', 'Technical Writer', 'persona-technical-writer-workflow'),
    ('test-engineer', 'Test Engineer', 'persona-test-engineer-workflow'),
    ('ui-ux-designer', 'UI/UX Designer', 'persona-ui-ux-designer-workflow')
]

print("🚀 Populating persona types...")

for type_name, display_name, workflow_id in persona_types:
    # Load the workflow YAML to get default capabilities
    workflow_path = Path(f"workflows/personas/{workflow_id}.yaml")
    default_capabilities = {}
    
    try:
        with open(workflow_path, 'r') as f:
            workflow_data = yaml.safe_load(f)
            
        # Extract skills as default capabilities
        persona_info = workflow_data.get('metadata', {}).get('persona_info', {})
        skills = persona_info.get('skills', [])
        default_capabilities = {
            'skills': skills,
            'role': persona_info.get('role', display_name),
            'email_pattern': f"{type_name.replace('-', '.')}@company.com"
        }
    except Exception as e:
        print(f"  ⚠️  Could not load workflow for {type_name}: {e}")
        default_capabilities = {
            'skills': [],
            'role': display_name,
            'email_pattern': f"{type_name.replace('-', '.')}@company.com"
        }
    
    # Insert or update persona type
    cur.execute("""
        INSERT INTO orchestrator.persona_types (type_name, display_name, base_workflow_id, default_capabilities)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (type_name) DO UPDATE
        SET display_name = %s, 
            base_workflow_id = %s,
            default_capabilities = %s
    """, (
        type_name, 
        display_name, 
        workflow_id,
        json.dumps(default_capabilities),
        display_name,
        workflow_id,
        json.dumps(default_capabilities)
    ))
    
    print(f"  ✅ {display_name} ({type_name})")

# Commit changes
conn.commit()

# Verify
cur.execute("SELECT COUNT(*) FROM orchestrator.persona_types")
count = cur.fetchone()[0]
print(f"\n✅ Total persona types in database: {count}")

# Show a sample
print("\n📋 Sample persona types:")
cur.execute("""
    SELECT type_name, display_name, base_workflow_id 
    FROM orchestrator.persona_types 
    ORDER BY display_name 
    LIMIT 5
""")
for row in cur.fetchall():
    print(f"  - {row[1]} ({row[0]}) -> {row[2]}")

cur.close()
conn.close()