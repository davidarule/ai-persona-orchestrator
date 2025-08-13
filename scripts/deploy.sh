#!/bin/bash
set -e

echo "🚀 Starting AI Persona Orchestrator Deployment"

# Load environment variables
source .env.production

# Generate SSL certificates if not exists
if [ ! -f "./ssl/cert.pem" ]; then
    echo "📜 Generating SSL certificates..."
    openssl req -x509 -newkey rsa:4096 -keyout ./ssl/key.pem -out ./ssl/cert.pem \
        -days 365 -nodes -subj "/CN=localhost"
fi

# Initialize databases
echo "🗄️ Initializing databases..."
docker compose up -d postgres neo4j redis
sleep 10

# Run database migrations
echo "📊 Running database migrations..."
docker compose exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB -f /docker-entrypoint-initdb.d/init.sql

# Start Camunda Platform
echo "⚙️ Starting Camunda Platform..."
docker compose -f docker/docker compose.camunda.yml up -d
sleep 20

# Deploy BPMN workflows
echo "📋 Deploying BPMN workflows..."
python scripts/deploy_workflows.py

# Start application services
echo "🎯 Starting application services..."
docker compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
./scripts/health_check.sh

echo "✅ Deployment complete!"
echo "📍 Access points:"
echo "   - Frontend: https://localhost:3000"
echo "   - Camunda Operate: http://localhost:8081"
echo "   - Grafana: http://localhost:3001"
echo "   - Neo4j Browser: http://localhost:7474"