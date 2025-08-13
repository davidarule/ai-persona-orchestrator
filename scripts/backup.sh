#!/bin/bash

# Configuration
BACKUP_DIR="/backup/ai-orchestrator"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/$TIMESTAMP"

# Load environment variables
source .env

echo "🔄 Starting backup at $TIMESTAMP"

# Create backup directory
mkdir -p $BACKUP_PATH

# Backup databases
echo "📦 Backing up PostgreSQL..."
docker compose exec -T postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB > $BACKUP_PATH/postgres.sql

echo "📦 Backing up Neo4j..."
docker compose exec -T neo4j neo4j-admin database dump neo4j --to-path=/backup/neo4j_$TIMESTAMP.dump
docker cp ai_orchestrator_neo4j:/backup/neo4j_$TIMESTAMP.dump $BACKUP_PATH/

echo "📦 Backing up Redis..."
docker compose exec -T redis redis-cli --rdb /data/backup_$TIMESTAMP.rdb BGSAVE
sleep 2
docker cp ai_orchestrator_redis:/data/backup_$TIMESTAMP.rdb $BACKUP_PATH/redis.rdb

# Backup configurations and workflows
echo "📦 Backing up configurations..."
cp -r ./config $BACKUP_PATH/ 2>/dev/null || true
cp -r ./workflows $BACKUP_PATH/
cp .env $BACKUP_PATH/.env.backup

# Compress backup
echo "🗜️ Compressing backup..."
tar -czf $BACKUP_PATH.tar.gz -C $BACKUP_DIR $TIMESTAMP
rm -rf $BACKUP_PATH

echo "✅ Backup completed: $BACKUP_PATH.tar.gz"

# Keep only last 7 days of backups
echo "🧹 Cleaning old backups..."
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "📊 Backup sizes:"
ls -lh $BACKUP_DIR/*.tar.gz | tail -5
