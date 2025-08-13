#!/usr/bin/env python3
import os
import yaml
import subprocess

def load_workflow(filepath, workflow_type):
    """Load a single workflow file into the database"""
    with open(filepath, 'r') as f:
        content = f.read()
        # Escape single quotes for SQL
        content = content.replace("'", "''")
        
    filename = os.path.basename(filepath)
    name = filename.replace('.yaml', '')
    
    sql = f"""
    INSERT INTO orchestrator.workflow_definitions (name, version, definition_yaml, is_active)
    VALUES ('{name}', '1.0.0', '{content}', true)
    ON CONFLICT (name) DO UPDATE 
    SET definition_yaml = EXCLUDED.definition_yaml,
        version = EXCLUDED.version,
        updated_at = CURRENT_TIMESTAMP;
    """
    
    # Execute SQL through docker
    cmd = ['docker', 'compose', 'exec', '-T', 'postgres', 
           'psql', '-U', 'orchestrator_user', '-d', 'ai_orchestrator']
    
    result = subprocess.run(cmd, input=sql, text=True, capture_output=True)
    
    if result.returncode == 0:
        print(f"  ✓ Loaded {workflow_type} workflow: {name}")
    else:
        print(f"  ✗ Failed to load {name}: {result.stderr}")

# Load system workflows
print("📋 Loading system workflows...")
for file in os.listdir('workflows/system'):
    if file.endswith('.yaml'):
        load_workflow(os.path.join('workflows/system', file), 'system')

# Load persona workflows  
print("\n👥 Loading persona workflows...")
for file in os.listdir('workflows/personas'):
    if file.endswith('.yaml'):
        load_workflow(os.path.join('workflows/personas', file), 'persona')

# Show count
print("\n📊 Checking loaded workflows...")
cmd = ['docker', 'compose', 'exec', '-T', 'postgres',
       'psql', '-U', 'orchestrator_user', '-d', 'ai_orchestrator',
       '-c', 'SELECT COUNT(*) as count FROM orchestrator.workflow_definitions;']
subprocess.run(cmd)
