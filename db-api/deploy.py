#!/usr/bin/env python3
"""
deploy.py - Deploy PostgreSQL CDC replication to Snowflake

Prerequisites: Run `terraform apply` first to create infrastructure.

This script:
1. Deploys Snowpark procedures
2. Creates WAL replication slots in each PostgreSQL database
3. Loads configuration from YAML into registry tables
4. Creates target schemas from config
5. Creates scheduled task DAG

Usage:
    python deploy.py --connection myconnection
"""

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml required. Install with: pip install pyyaml")
    sys.exit(1)

try:
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("ERROR: snowflake-connector-python and cryptography required")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("ERROR: psycopg2 required. Install with: pip install psycopg2-binary")
    sys.exit(1)


def get_connection_params(connection_name: str) -> dict:
    config_path = Path.home() / ".snowflake" / "config.toml"
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    
    conn_config = config.get("connections", {}).get(connection_name, {})
    if not conn_config:
        raise ValueError(f"Connection '{connection_name}' not found in config.toml")
    
    params = {
        "account": conn_config.get("account"),
        "user": conn_config.get("user"),
        "role": conn_config.get("role"),
        "warehouse": conn_config.get("warehouse"),
        "database": conn_config.get("database"),
        "schema": conn_config.get("schema"),
    }
    
    if conn_config.get("authenticator") == "SNOWFLAKE_JWT":
        key_path = conn_config.get("private_key_path")
        if key_path:
            with open(key_path, "rb") as f:
                private_key = serialization.load_pem_private_key(
                    f.read(), password=None, backend=default_backend()
                )
            params["private_key"] = private_key
    elif conn_config.get("password"):
        params["password"] = conn_config.get("password")
    
    return {k: v for k, v in params.items() if v is not None}


def run_sql(conn, sql: str, description: str = None):
    if description:
        print(f"  {description}...", end=" ", flush=True)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        result = cur.fetchone()
        if description:
            print("✓")
        return result
    except Exception as e:
        if description:
            print(f"✗ ({e})")
        raise


def setup_wal_slots(databases: list, pg_user: str, pg_password: str) -> dict:
    """
    Create WAL replication slots in each PostgreSQL database.
    
    IMPORTANT: Each slot must be created while connected to its target database.
    A slot created in database A cannot replicate tables from database B.
    """
    results = {"created": [], "existing": [], "errors": []}
    
    for db in databases:
        slot_name = db.get("wal_slot")
        if not slot_name:
            continue
            
        host = db.get("host")
        db_name = db.get("source_db_name")
        
        try:
            conn = psycopg2.connect(
                host=host,
                database=db_name,
                user=pg_user,
                password=pg_password,
                connect_timeout=10
            )
            cur = conn.cursor()
            
            cur.execute(
                "SELECT slot_name, database FROM pg_replication_slots WHERE slot_name = %s",
                (slot_name,)
            )
            existing = cur.fetchone()
            
            if existing:
                if existing[1] == db_name:
                    results["existing"].append(f"{slot_name} ({db_name})")
                else:
                    cur.execute("SELECT pg_drop_replication_slot(%s)", (slot_name,))
                    conn.commit()
                    cur.execute(
                        "SELECT pg_create_logical_replication_slot(%s, %s)",
                        (slot_name, "test_decoding")
                    )
                    conn.commit()
                    results["created"].append(f"{slot_name} ({db_name}) [recreated - was in {existing[1]}]")
            else:
                cur.execute(
                    "SELECT pg_create_logical_replication_slot(%s, %s)",
                    (slot_name, "test_decoding")
                )
                conn.commit()
                results["created"].append(f"{slot_name} ({db_name})")
            
            cur.close()
            conn.close()
            
        except Exception as e:
            results["errors"].append(f"{slot_name} ({db_name}): {e}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Deploy PostgreSQL CDC replication")
    parser.add_argument("--connection", "-c", required=True, help="Snowflake connection name")
    parser.add_argument("--config", default="config/replication_config.yaml", help="YAML config file")
    parser.add_argument("--skip-procedures", action="store_true", help="Skip procedure deployment")
    parser.add_argument("--skip-dag", action="store_true", help="Skip DAG creation")
    parser.add_argument("--skip-wal-slots", action="store_true", help="Skip WAL slot creation")
    parser.add_argument("--pg-user", default="snowflake_admin", help="PostgreSQL username")
    parser.add_argument("--pg-password", help="PostgreSQL password (or set PG_PASSWORD env var)")
    args = parser.parse_args()

    import os
    pg_password = args.pg_password or os.environ.get("PG_PASSWORD")
    if not pg_password and not args.skip_wal_slots:
        print("ERROR: PostgreSQL password required. Use --pg-password or set PG_PASSWORD env var")
        print("       Or use --skip-wal-slots to skip WAL slot setup")
        sys.exit(1)

    script_dir = Path(__file__).parent
    config_path = script_dir / args.config

    if not config_path.exists():
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    print(f"\n📄 Loading config from {config_path}")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    for t in config.get("tables", []):
        t.pop("description", None)

    databases = config.get("databases", [])
    tables = config.get("tables", [])
    print(f"   Found {len(databases)} database(s), {len(tables)} table(s)")

    print(f"\n🔌 Connecting to Snowflake (connection: {args.connection})")
    conn_params = get_connection_params(args.connection)
    conn = snowflake.connector.connect(**conn_params)

    # Step 1: Deploy procedures
    if not args.skip_procedures:
        print("\n🚀 Step 1: Deploying Snowpark procedures")
        result = subprocess.run(
            ["snow", "snowpark", "deploy", "-p", str(script_dir), "--replace", "-c", args.connection],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  ✓ Procedures deployed successfully")
        else:
            print(f"  ✗ Deployment failed: {result.stderr}")
            sys.exit(1)
    else:
        print("\n⏭️  Step 1: Skipping procedure deployment")

    # Step 2: Create WAL replication slots
    if not args.skip_wal_slots:
        print("\n🔄 Step 2: Creating WAL replication slots")
        wal_results = setup_wal_slots(databases, args.pg_user, pg_password)
        
        for slot in wal_results["existing"]:
            print(f"  ✓ {slot} (exists)")
        for slot in wal_results["created"]:
            print(f"  ✓ {slot} (created)")
        for error in wal_results["errors"]:
            print(f"  ✗ {error}")
        
        if wal_results["errors"]:
            print("  ⚠️  Some WAL slots failed - WAL sync may not work for those databases")
    else:
        print("\n⏭️  Step 2: Skipping WAL slot creation")

    # Step 3: Load configuration into registry
    print("\n⚙️  Step 3: Loading replication configuration")
    config_json = json.dumps(config)
    cur = conn.cursor()
    cur.execute(f"CALL DBAPI_REPLICA_DB.UTILS.SETUP_REPLICATION('{config_json}')")
    result = cur.fetchone()[0]
    db_count = result.count("DATABASE:")
    table_count = result.count("TABLE:")
    print(f"  ✓ Configured {db_count} database(s), {table_count} table(s)")

    # Step 4: Create target schemas from config
    print("\n📁 Step 4: Creating target schemas")
    for db in databases:
        schema = db.get("target_schema")
        if schema:
            run_sql(conn, f"CREATE SCHEMA IF NOT EXISTS DBAPI_REPLICA_DB.{schema}", f"Creating {schema}")

    # Step 5: Create task DAG
    if not args.skip_dag:
        print("\n📅 Step 5: Creating scheduled task DAG")
        
        cur.execute("""
            SELECT TABLE_ID, DATABASE_ID 
            FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY 
            WHERE SYNC_ENABLED = TRUE
            ORDER BY DATABASE_ID, TABLE_ID
        """)
        all_tables = cur.fetchall()

        run_sql(conn, """
            CREATE OR REPLACE TASK DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG
                WAREHOUSE = COMPUTE_WH
                SCHEDULE = '15 MINUTE'
            AS SELECT 'CDC Sync DAG Root' AS status
        """, "Creating root task CDC_SYNC_DAG")

        for table_id, database_id in all_tables:
            task_name = f"TASK_{table_id.upper().replace('-', '_')}"
            run_sql(conn, f"""
                CREATE OR REPLACE TASK DBAPI_REPLICA_DB.UTILS.{task_name}
                    WAREHOUSE = COMPUTE_WH
                    AFTER DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG
                AS CALL DBAPI_REPLICA_DB.UTILS.SYNC_SINGLE_TABLE('{database_id}', '{table_id}')
            """, f"Creating task {task_name}")

        print(f"  ✓ Created {len(all_tables)} child tasks")

        task_names = [f"TASK_{t[0].upper().replace('-', '_')}" for t in all_tables]
        after_clause = ", ".join([f"DBAPI_REPLICA_DB.UTILS.{t}" for t in task_names])
        run_sql(conn, f"""
            CREATE OR REPLACE TASK DBAPI_REPLICA_DB.UTILS.TASK_CONSOLIDATE_SYNC_LOG
                WAREHOUSE = COMPUTE_WH
                AFTER {after_clause}
            AS CALL DBAPI_REPLICA_DB.UTILS.CONSOLIDATE_SYNC_LOG()
        """, "Creating consolidation task")

        print("  Resuming all child tasks...")
        for task_name in task_names:
            cur.execute(f"ALTER TASK DBAPI_REPLICA_DB.UTILS.{task_name} RESUME")
        cur.execute("ALTER TASK DBAPI_REPLICA_DB.UTILS.TASK_CONSOLIDATE_SYNC_LOG RESUME")
        print(f"  ✓ Resumed {len(task_names) + 1} child tasks")
        
        run_sql(conn, "ALTER TASK DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG RESUME", "Resuming root task")
    else:
        print("\n⏭️  Step 5: Skipping DAG creation")

    # Verify
    print("\n✅ Verification")
    cur.execute("CALL DBAPI_REPLICA_DB.UTILS.CHECK_PG_HEALTH()")
    health = cur.fetchone()[0]
    if "Error" in health:
        print(f"  ⚠️  PostgreSQL: {health}")
    else:
        print(f"  ✓ PostgreSQL connected")
        if "Slot Names:" in health:
            slots = health.split("Slot Names: ")[1] if "Slot Names:" in health else ""
            print(f"  ✓ WAL slots: {slots}")

    cur.execute("SELECT COUNT(*) FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY WHERE SYNC_ENABLED = TRUE")
    print(f"  ✓ {cur.fetchone()[0]} tables ready for sync")

    print("\n🎉 Deployment complete!")
    print("\nNext steps:")
    print("  - Run initial sync: EXECUTE TASK DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG")
    print("  - Or use demo script: ./scripts/demo.sh sync")
    conn.close()


if __name__ == "__main__":
    main()
