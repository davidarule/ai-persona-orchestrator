#!/usr/bin/env python3
import psycopg2
import yaml

conn = psycopg2.connect(
    host='localhost', 
    port='5434', 
    database='ai_orchestrator', 
    user='orchestrator_user', 
    password='Drool00!425938'
)
cur = conn.cursor()

for filename in ['workflows/personas/persona-security-architect-workflow.yaml', 
                 'workflows/personas/persona-security-engineer-workflow.yaml']:
    with open(filename, 'r') as f:
        content = f.read()
        data = yaml.safe_load(content)
    
    name = data['metadata']['name']
    version = data['metadata']['version']
    
    cur.execute('''
        INSERT INTO orchestrator.workflow_definitions (name, version, definition_yaml, is_active)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE 
        SET definition_yaml = %s, version = %s, updated_at = CURRENT_TIMESTAMP
    ''', (name, version, content, True, content, version))
    
    print(f'✅ Deployed: {name}')

conn.commit()
conn.close()