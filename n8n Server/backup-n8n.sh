#!/bin/bash

# Configuration
BACKUP_DIR="/home/debian/backups"
N8N_DIR="/home/debian/n8n"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_PATH="$BACKUP_DIR/$DATE"
POSTGRES_CONTAINER="n8n-postgres-1" # Check container name with /usr/bin/docker ps
DB_USER="root" # From .env
DB_NAME="n8n"  # From .env

# Create backup directory
mkdir -p "$BACKUP_PATH"

echo "Starting backup for $DATE..."

# 1. Backup PostgreSQL Database
echo "Backing up database..."
if /usr/bin/docker exec "$POSTGRES_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" > "$BACKUP_PATH/database.sql"; then
    echo "Database backup successful."
else
    echo "Error backing up database!"
    exit 1
fi

# 2. Backup Configuration Files
echo "Backing up configuration files..."
cp "$N8N_DIR/.env" "$BACKUP_PATH/.env"
cp "$N8N_DIR//usr/bin/docker-compose.yml" "$BACKUP_PATH//usr/bin/docker-compose.yml"

# 3. Compress Backup
echo "Compressing backup..."
tar -czf "$BACKUP_DIR/n8n_backup_$DATE.tar.gz" -C "$BACKUP_DIR" "$DATE"
rm -rf "$BACKUP_PATH" # Remove uncompressed directory

# 4. Cleanup old backups (keep last 7 days)
echo "Cleaning up old backups..."
find "$BACKUP_DIR" -name "n8n_backup_*.tar.gz" -mtime +7 -delete

echo "Backup completed successfully: $BACKUP_DIR/n8n_backup_$DATE.tar.gz"
