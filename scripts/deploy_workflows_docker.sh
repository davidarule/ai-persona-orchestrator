#!/bin/bash

echo "🚀 Deploying workflows to database..."

# Deploy each system workflow
for file in workflows/system/*.yaml; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        echo "  📄 Deploying system workflow: $filename"
        
        # Insert into database
        docker compose exec -T postgres psql -U orchestrator_user -d ai_orchestrator << SQL
INSERT INTO orchestrator.workflow_definitions (name, version, definition_yaml, is_active)
VALUES ('${filename%.yaml}', '1.0.0', 
        pg_read_file('/app/workflows/system/$filename')::text, true)
ON CONFLICT (name) DO UPDATE 
SET definition_yaml = EXCLUDED.definition_yaml,
    version = EXCLUDED.version,
    updated_at = CURRENT_TIMESTAMP;
SQL
    fi
done

# Deploy each persona workflow  
for file in workflows/personas/*.yaml; do
    if [ -f "$file" ]; then
        filename=$(basename "$file")
        echo "  👤 Deploying persona workflow: $filename"
        
        # Insert into database
        docker compose exec -T postgres psql -U orchestrator_user -d ai_orchestrator << SQL
INSERT INTO orchestrator.workflow_definitions (name, version, definition_yaml, is_active)
VALUES ('${filename%.yaml}', '1.0.0',
        pg_read_file('/app/workflows/personas/$filename')::text, true)
ON CONFLICT (name) DO UPDATE
SET definition_yaml = EXCLUDED.definition_yaml,
    version = EXCLUDED.version,
    updated_at = CURRENT_TIMESTAMP;
SQL
    fi
done

echo "✅ Workflow deployment complete!"

# Show count of deployed workflows
docker compose exec -T postgres psql -U orchestrator_user -d ai_orchestrator << SQL
SELECT 'Deployed workflows:' as status, COUNT(*) as count 
FROM orchestrator.workflow_definitions;
SQL
