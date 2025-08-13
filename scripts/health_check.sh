#!/bin/bash

services=("postgres:5432" "redis:6379" "neo4j:7687" "backend:8000" "frontend:3000")

for service in "${services[@]}"; do
    IFS=':' read -r name port <<< "$service"
    echo -n "Checking $name... "
    
    for i in {1..30}; do
        if nc -z localhost $port 2>/dev/null; then
            echo "✓"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "✗ Failed to start"
            exit 1
        fi
        sleep 2
    done
done

echo "All services healthy!"