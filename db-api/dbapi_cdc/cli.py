"""
CLI for dbapi-cdc replication.

Uses the session module for flexible connection handling.

Usage:
    # Using Snow CLI connection name
    dbapi-cdc sync --config config.yaml --connection myconnection
    
    # Full refresh
    dbapi-cdc sync --config config.yaml --full-refresh
    
    # Status
    dbapi-cdc status --config config.yaml
    
    # Registry-based sync (uses DATABASE_REGISTRY/TABLE_REGISTRY)
    dbapi-cdc sync-registry --database-id blfra_prod --table-id blfra_prod_rec_items
"""

import argparse
import json
import os
import sys

from .session import get_session, SessionContext


def cmd_sync(args):
    """Run replication using config file."""
    from .replicator import Replicator, load_config

    with SessionContext(connection_name=args.connection) as session:
        config = load_config(args.config)
        replicator = Replicator(session, config)

        print(f"Config: {args.config}")
        print(f"Full refresh: {args.full_refresh}")

        if args.database and args.table:
            db = next((d for d in config.databases if d.name == args.database), None)
            if not db:
                print(f"Database not found: {args.database}", file=sys.stderr)
                sys.exit(1)
            table = next((t for t in db.tables if t.name == args.table), None)
            if not table:
                print(f"Table not found: {args.table}", file=sys.stderr)
                sys.exit(1)
            results = [replicator.sync_table(args.database, table, args.full_refresh)]
        elif args.database:
            db = next((d for d in config.databases if d.name == args.database), None)
            if not db:
                print(f"Database not found: {args.database}", file=sys.stderr)
                sys.exit(1)
            results = replicator.sync_database(db, args.full_refresh)
        else:
            results = replicator.sync_all(args.full_refresh)

        print(f"\n{'Database':<20} {'Table':<20} {'Status':<10} {'Rows':>10}")
        print("-" * 65)
        for r in results:
            status = r["status"]
            rows = r.get("rows", "-")
            print(f"{r['database']:<20} {r['table']:<20} {status:<10} {rows:>10}")

        failed = sum(1 for r in results if r["status"] == "failed")
        if failed:
            sys.exit(1)


def cmd_sync_registry(args):
    """
    Run sync using DATABASE_REGISTRY and TABLE_REGISTRY.
    
    This is the same logic as the stored procedure, for local testing.
    """
    from .procedures import sync_single_table
    
    # For local testing, we need to mock _snowflake.get_username_password
    # Get credentials from environment instead
    os.environ.setdefault("PG_USER", os.getenv("PGUSER", ""))
    os.environ.setdefault("PG_PASSWORD", os.getenv("PGPASSWORD", ""))
    
    with SessionContext(connection_name=args.connection) as session:
        if args.table_id:
            # Sync single table
            result = sync_single_table(session, args.database_id, args.table_id)
            print(result)
        else:
            # Sync all tables for database
            tables = session.sql(f"""
                SELECT TABLE_ID FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
                WHERE DATABASE_ID = '{args.database_id}' AND SYNC_ENABLED = TRUE
            """).collect()
            
            for row in tables:
                table_id = row['TABLE_ID']
                print(f"Syncing {table_id}...")
                result = sync_single_table(session, args.database_id, table_id)
                print(result)
                print()


def cmd_status(args):
    """Show replication status from registry."""
    with SessionContext(connection_name=args.connection) as session:
        result = session.sql("""
            SELECT * FROM DBAPI_REPLICA_DB.UTILS.MULTI_DB_SYNC_STATUS
            ORDER BY DATABASE_ID
        """).collect()

        if not result:
            print("No sync status found")
            return

        print(f"\n{'Database':<15} {'Schema':<15} {'Tables':>7} {'Synced':>7} {'Rows':>12} {'Last Sync'}")
        print("-" * 80)
        for row in result:
            last_sync = str(row['LAST_SYNC_TIME'])[:19] if row['LAST_SYNC_TIME'] else "-"
            print(
                f"{row['DATABASE_ID']:<15} "
                f"{row['TARGET_SCHEMA']:<15} "
                f"{row['TABLE_COUNT']:>7} "
                f"{row['SYNCED_TABLES']:>7} "
                f"{row['TOTAL_ROWS']:>12,} "
                f"{last_sync}"
            )


def cmd_test_connection(args):
    """Test PostgreSQL connection via Snowflake."""
    with SessionContext(connection_name=args.connection) as session:
        # Get host from registry
        result = session.sql(f"""
            SELECT HOST, SOURCE_DB_NAME 
            FROM DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY
            WHERE DATABASE_ID = '{args.database_id}'
        """).collect()
        
        if not result:
            print(f"Database '{args.database_id}' not found in registry")
            sys.exit(1)
        
        host = result[0]['HOST']
        dbname = result[0]['SOURCE_DB_NAME']
        
        print(f"Testing connection to {host}/{dbname}...")
        
        import psycopg2
        
        conn = psycopg2.connect(
            host=host,
            port=5432,
            dbname=dbname,
            user=os.getenv("PGUSER"),
            password=os.getenv("PGPASSWORD"),
            sslmode='require'
        )
        cursor = conn.cursor()
        
        cursor.execute("SELECT version()")
        print(f"PostgreSQL: {cursor.fetchone()[0][:50]}...")
        
        cursor.execute(f"SELECT pg_size_pretty(pg_database_size('{dbname}'))")
        print(f"Database size: {cursor.fetchone()[0]}")
        
        cursor.close()
        conn.close()
        print("Connection successful!")


def main():
    parser = argparse.ArgumentParser(
        description="DB-API CDC: Replicate external databases to Snowflake"
    )
    parser.add_argument(
        "--connection", "-c",
        default=os.getenv("SNOWFLAKE_CONNECTION_NAME", "myconnection"),
        help="Snow CLI connection name (default: $SNOWFLAKE_CONNECTION_NAME or 'myconnection')"
    )
    
    sub = parser.add_subparsers(dest="command", required=True)

    # Config-based sync
    sync = sub.add_parser("sync", help="Run replication from config file")
    sync.add_argument("--config", required=True, help="Path to config file")
    sync.add_argument("--database", help="Sync specific database")
    sync.add_argument("--table", help="Sync specific table (requires --database)")
    sync.add_argument("--full-refresh", action="store_true", help="Force full refresh")

    # Registry-based sync (matches stored procedure behavior)
    sync_reg = sub.add_parser("sync-registry", help="Run sync using DATABASE_REGISTRY/TABLE_REGISTRY")
    sync_reg.add_argument("--database-id", required=True, help="DATABASE_ID from registry")
    sync_reg.add_argument("--table-id", help="TABLE_ID from registry (optional, syncs all if omitted)")

    # Status
    status = sub.add_parser("status", help="Show sync status from MULTI_DB_SYNC_STATUS view")

    # Test connection
    test = sub.add_parser("test-connection", help="Test PostgreSQL connection")
    test.add_argument("--database-id", required=True, help="DATABASE_ID to test")

    args = parser.parse_args()
    
    if args.command == "sync":
        cmd_sync(args)
    elif args.command == "sync-registry":
        cmd_sync_registry(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "test-connection":
        cmd_test_connection(args)


if __name__ == "__main__":
    main()
