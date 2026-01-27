"""
CLI for dbapi-cdc replication.

Usage:
    dbapi-cdc sync --config config.yaml
    dbapi-cdc sync --config config.yaml --full-refresh
    dbapi-cdc status --config config.yaml
"""

import argparse
import os
import sys


def get_session():
    """Create Snowpark session from connection name."""
    import snowflake.connector
    from snowflake.snowpark import Session

    name = os.getenv("SNOWFLAKE_CONNECTION_NAME", "default")
    try:
        conn = snowflake.connector.connect(connection_name=name)
        return Session.builder.configs({"connection": conn}).create()
    except Exception as e:
        print(f"Failed to connect: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_sync(args):
    """Run replication."""
    from .replicator import Replicator, load_config

    session = get_session()
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


def cmd_status(args):
    """Show replication status."""
    from .replicator import Replicator, load_config

    session = get_session()
    config = load_config(args.config)
    replicator = Replicator(session, config)

    status = replicator.status()
    if not status:
        print("No replication state found")
        return

    print(f"\n{'Source DB':<20} {'Table':<20} {'Status':<12} {'Rows':>10} {'Watermark'}")
    print("-" * 85)
    for s in status:
        wm = s["watermark"][:19] if s["watermark"] else "-"
        rows = s["rows"] if s["rows"] else "-"
        print(f"{s['source_db']:<20} {s['table']:<20} {s['status']:<12} {rows:>10} {wm}")


def main():
    parser = argparse.ArgumentParser(description="CDC Replication: External DB to Snowflake")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Run replication")
    sync.add_argument("--config", required=True, help="Path to config file")
    sync.add_argument("--database", help="Sync specific database")
    sync.add_argument("--table", help="Sync specific table (requires --database)")
    sync.add_argument("--full-refresh", action="store_true", help="Force full refresh")

    status = sub.add_parser("status", help="Show replication status")
    status.add_argument("--config", required=True, help="Path to config file")

    args = parser.parse_args()
    if args.command == "sync":
        cmd_sync(args)
    elif args.command == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
