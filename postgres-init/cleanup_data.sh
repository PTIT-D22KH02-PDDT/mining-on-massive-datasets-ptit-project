#!/bin/bash
# =============================================================================
# Data Retention Policy - Cleanup Script
# Phase 6.1: Periodic cleanup to prevent unbounded table growth
# Run via cron: 0 2 * * * /path/to/cleanup_data.sh
# =============================================================================

set -e

# Configuration
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-otto}"
DB_NAME="${POSTGRES_DB:-otto_recommender}"
DB_PASS="${POSTGRES_PASSWORD:-otto123}"

export PGPASSWORD="$DB_PASS"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting data cleanup..."

# Run cleanup SQL
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$(dirname "$0")/02_cleanup_old_data.sql"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Data cleanup completed."