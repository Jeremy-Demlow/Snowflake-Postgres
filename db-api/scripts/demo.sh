#!/bin/bash
# =============================================================================
# PostgreSQL → Snowflake CDC Demo Scripts
# =============================================================================
# Quick scripts to showcase the replication solution
#
# Usage:
#   ./demo.sh setup      - Full teardown and rebuild
#   ./demo.sh update     - Update PostgreSQL data
#   ./demo.sh sync       - Run sync tasks
#   ./demo.sh verify     - Check sync status
#   ./demo.sh full-demo  - Complete demo flow (update + sync + verify)
# =============================================================================

set -e

# Configuration (use environment variables)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TERRAFORM_DIR="$PROJECT_DIR/terraform"
CONNECTION_NAME="${SNOWFLAKE_CONNECTION:-myconnection}"

PG_HOST="${PG_HOST:-your_pg_host}"
PG_USER="${PG_USER:-snowflake_admin}"
PG_PASSWORD="${PG_PASSWORD:-your_pg_password}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $1"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)]${NC} $1"; }
error() { echo -e "${RED}[$(date +%H:%M:%S)]${NC} $1"; exit 1; }

check_pg_env() {
    if [[ "$PG_HOST" == "your_pg_host" ]] || [[ "$PG_PASSWORD" == "your_pg_password" ]]; then
        error "Please set PG_HOST and PG_PASSWORD environment variables"
    fi
}

run_pg() {
    local db="$1"
    local sql="$2"
    PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -U "$PG_USER" -d "$db" -c "$sql" 2>/dev/null
}

show_help() {
    echo "PostgreSQL → Snowflake CDC Demo"
    echo ""
    echo "Usage: ./demo.sh <command>"
    echo ""
    echo "Commands:"
    echo "  sync       - Trigger CDC_SYNC_DAG task"
    echo "  verify     - Check sync status"
    echo "  update     - Insert test data into PostgreSQL"
    echo "  full-demo  - Run update + sync + verify"
    echo ""
    echo "Environment variables:"
    echo "  PG_HOST      - PostgreSQL host"
    echo "  PG_USER      - PostgreSQL user (default: snowflake_admin)"
    echo "  PG_PASSWORD  - PostgreSQL password"
    echo "  SNOWFLAKE_CONNECTION - Connection name (default: myconnection)"
}

cmd_sync() {
    log "Triggering CDC sync DAG..."
    snow sql -c "$CONNECTION_NAME" -q "EXECUTE TASK DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG"
    log "Sync triggered. Run './demo.sh verify' in ~20 seconds to check status."
}

cmd_verify() {
    log "Checking sync status..."
    snow sql -c "$CONNECTION_NAME" -q "
        SELECT 
            COUNT(CASE WHEN SYNC_STATUS = 'success' THEN 1 END) as SUCCESS,
            COUNT(CASE WHEN SYNC_STATUS LIKE 'error%' THEN 1 END) as ERRORS,
            SUM(SYNC_RECORDS) as ROWS_SYNCED
        FROM DBAPI_REPLICA_DB.UTILS.SYNC_LOG 
        WHERE LOGGED_AT > DATEADD(minute, -2, CURRENT_TIMESTAMP())
    "
}

cmd_update() {
    check_pg_env
    log "Inserting test data into PostgreSQL..."
    
    for db in customer_a_db customer_b_db customer_c_db; do
        log "Updating $db..."
        run_pg "$db" "INSERT INTO data.os_currencies (currency_code, description) VALUES ('TST', 'Test Currency $(date +%s)') ON CONFLICT DO NOTHING;"
    done
    
    log "Test data inserted. Run './demo.sh sync' to replicate."
}

cmd_full_demo() {
    cmd_update
    sleep 2
    cmd_sync
    sleep 20
    cmd_verify
}

case "${1:-help}" in
    sync) cmd_sync ;;
    verify) cmd_verify ;;
    update) cmd_update ;;
    full-demo) cmd_full_demo ;;
    *) show_help ;;
esac
