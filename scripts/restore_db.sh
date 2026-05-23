#!/bin/bash
# Database restore script for Smart Bed AI
# Restores from a timestamped PostgreSQL backup

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups/postgres}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-smart_bed_db}"
DB_USER="${DB_USER:-postgres}"

# Function to list available backups
list_backups() {
    echo "Available backups:"
    find "$BACKUP_DIR" -name "backup_${DB_NAME}_*.sql.gz" -type f | sort -r | nl
}

# Check if backup file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file>"
    echo ""
    list_backups
    echo ""
    echo "Example: $0 $BACKUP_DIR/backup_${DB_NAME}_20260515_233000.sql.gz"
    exit 1
fi

BACKUP_FILE="$1"

# Verify backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    list_backups
    exit 1
fi

# Verify backup integrity
echo "Verifying backup integrity..."
if ! gzip -t "$BACKUP_FILE"; then
    echo "Error: Backup file is corrupted!"
    exit 1
fi
echo "✓ Backup integrity verified"

# Warning prompt
echo ""
echo "WARNING: This will DROP and RECREATE the database: $DB_NAME"
echo "Backup file: $BACKUP_FILE"
echo ""
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo ""
echo "Starting database restore..."

# Decompress and restore
echo "Decompressing backup..."
gunzip -c "$BACKUP_FILE" | PGPASSWORD="${DB_PASSWORD}" psql \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --quiet

echo ""
echo "✓ Database restored successfully from: $BACKUP_FILE"

# Verify restore
echo ""
echo "Verifying restore..."
TABLE_COUNT=$(PGPASSWORD="${DB_PASSWORD}" psql \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

echo "✓ Found $TABLE_COUNT tables in restored database"
echo ""
echo "Restore completed successfully!"
