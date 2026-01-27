"""
Deploy dbapi_cdc to Snowflake with Task DAG orchestration.

Usage:
    cd db-api
    SNOWFLAKE_CONNECTION_NAME=myconnection python -m dbapi_cdc.deploy_to_snowflake
    SNOWFLAKE_CONNECTION_NAME=myconnection python -m dbapi_cdc.deploy_to_snowflake --dry-run
"""

import argparse
import os
import tempfile
import zipfile
from pathlib import Path

import yaml


def get_session():
    import snowflake.connector
    from snowflake.snowpark import Session
    connection_name = os.getenv("SNOWFLAKE_CONNECTION_NAME", "default")
    conn = snowflake.connector.connect(connection_name=connection_name)
    return Session.builder.configs({"connection": conn}).create()


def create_zip_package(output_path: str) -> str:
    """Create a zip of the dbapi_cdc package"""
    import dbapi_cdc
    pkg_dir = Path(dbapi_cdc.__file__).parent

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for py_file in pkg_dir.glob("*.py"):
            arcname = f"dbapi_cdc/{py_file.name}"
            zf.write(py_file, arcname)

    return output_path


def deploy(
    config_path: str = "config/replication_config.yaml",
    database: str = "DBAPI_REPLICA_DB",
    schema: str = "UTILS",
    stage: str = "CDC_STAGE",
    warehouse: str = "COMPUTE_WH",
    dry_run: bool = False,
):
    """Deploy dbapi_cdc stored procedures and Task DAG to Snowflake"""

    with open(config_path) as f:
        config = yaml.safe_load(f)

    eai = config["orchestration"]["external_access_integration"]
    secret = config["source"]["secret_name"]
    dag_name = config["orchestration"]["dag_name"]
    schedule = config["orchestration"]["schedule"]
    timeout_ms = config["orchestration"].get("user_task_timeout_ms", 3600000)

    with open(config_path) as f:
        config_yaml = f.read()
    config_yaml.replace("'", "''")

    def run_sql(sql: str, description: str = ""):
        if dry_run:
            print(f"\n-- {description}")
            print(sql.strip())
            print(";")
        else:
            session.sql(sql).collect()

    if dry_run:
        print("=" * 60)
        print("DRY RUN - SQL that would be executed:")
        print("=" * 60)
        session = None
    else:
        session = get_session()

    print(f"\n[1/5] Creating {database}.{schema} and stage...")
    run_sql(f"CREATE DATABASE IF NOT EXISTS {database}", "Create database")
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {database}.{schema}", "Create schema")
    run_sql(f"CREATE STAGE IF NOT EXISTS {database}.{schema}.{stage}", "Create stage")

    if not dry_run:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "dbapi_cdc.zip")
            print("[2/5] Creating and uploading package...")
            create_zip_package(zip_path)
            session.file.put(
                zip_path,
                f"@{database}.{schema}.{stage}",
                auto_compress=False,
                overwrite=True,
            )
    else:
        print("\n[2/5] Would upload dbapi_cdc.zip to stage...")
        print(f"-- PUT file://dbapi_cdc.zip @{database}.{schema}.{stage}")

    print("\n[3/5] Creating SYNC_TABLE procedure...")
    sync_table_sql = f"""
        CREATE OR REPLACE PROCEDURE {database}.{schema}.SYNC_TABLE(
            CONFIG_YAML STRING,
            SOURCE_DATABASE STRING,
            TABLE_NAME STRING,
            FULL_REFRESH BOOLEAN DEFAULT FALSE
        )
        RETURNS STRING
        LANGUAGE PYTHON
        RUNTIME_VERSION = '3.10'
        PACKAGES = ('snowflake-snowpark-python', 'pyyaml', 'psycopg2')
        IMPORTS = ('@{database}.{schema}.{stage}/dbapi_cdc.zip')
        EXTERNAL_ACCESS_INTEGRATIONS = ({eai})
        SECRETS = ('creds' = {secret})
        HANDLER = 'dbapi_cdc.procedures.sync_table'
    """
    run_sql(sync_table_sql, "Create SYNC_TABLE procedure")

    print("\n[4/5] Creating SYNC_ALL procedure...")
    sync_all_sql = f"""
        CREATE OR REPLACE PROCEDURE {database}.{schema}.SYNC_ALL(
            CONFIG_YAML STRING,
            FULL_REFRESH BOOLEAN DEFAULT FALSE
        )
        RETURNS STRING
        LANGUAGE PYTHON
        RUNTIME_VERSION = '3.10'
        PACKAGES = ('snowflake-snowpark-python', 'pyyaml', 'psycopg2')
        IMPORTS = ('@{database}.{schema}.{stage}/dbapi_cdc.zip')
        EXTERNAL_ACCESS_INTEGRATIONS = ({eai})
        SECRETS = ('creds' = {secret})
        HANDLER = 'dbapi_cdc.procedures.sync_all'
    """
    run_sql(sync_all_sql, "Create SYNC_ALL procedure")

    print("\n[5/5] Creating Task DAG...")

    run_sql(f"ALTER TASK IF EXISTS {database}.{schema}.{dag_name} SUSPEND", "Suspend existing DAG")
    for db_cfg in config["source"]["databases"]:
        for tbl in db_cfg["tables"]:
            task_name = f"{dag_name}_{db_cfg['name']}_{tbl['name']}".upper()
            run_sql(f"DROP TASK IF EXISTS {database}.{schema}.{task_name}", f"Drop child task {task_name}")
    run_sql(f"DROP TASK IF EXISTS {database}.{schema}.{dag_name}", "Drop root task")

    root_task_sql = f"""
        CREATE TASK {database}.{schema}.{dag_name}
        WAREHOUSE = {warehouse}
        SCHEDULE = 'USING CRON {schedule} UTC'
        USER_TASK_TIMEOUT_MS = {timeout_ms}
        AS
        SELECT 'CDC Replication DAG Started' as status
    """
    run_sql(root_task_sql, "Create root task")

    child_tasks = []
    for db_cfg in config["source"]["databases"]:
        for tbl in db_cfg["tables"]:
            task_name = f"{dag_name}_{db_cfg['name']}_{tbl['name']}".upper()
            child_tasks.append(task_name)

            child_sql = f"""
                CREATE TASK {database}.{schema}.{task_name}
                WAREHOUSE = {warehouse}
                USER_TASK_TIMEOUT_MS = {timeout_ms}
                AFTER {database}.{schema}.{dag_name}
                AS
                CALL {database}.{schema}.SYNC_TABLE(
                    $${config_yaml}$$,
                    '{db_cfg["name"]}',
                    '{tbl["name"]}',
                    FALSE
                )
            """
            run_sql(child_sql, f"Create child task {task_name}")

    for task_name in child_tasks:
        run_sql(f"ALTER TASK {database}.{schema}.{task_name} RESUME", f"Resume {task_name}")
    run_sql(f"ALTER TASK {database}.{schema}.{dag_name} RESUME", "Resume root task")

    print("\n" + "="*60)
    if dry_run:
        print("DRY RUN COMPLETE - No changes made")
    else:
        print("DEPLOYMENT COMPLETE!")
    print("="*60)
    print("\nProcedures:")
    print(f"  - {database}.{schema}.SYNC_TABLE(config, db, table, full_refresh)")
    print(f"  - {database}.{schema}.SYNC_ALL(config, full_refresh)")
    print(f"\nTask DAG: {database}.{schema}.{dag_name}")
    print(f"  Schedule: {schedule}")
    print(f"  Child Tasks: {len(child_tasks)}")
    for t in child_tasks:
        print(f"    - {t}")
    print("\nTo manually trigger:")
    print(f"  EXECUTE TASK {database}.{schema}.{dag_name};")

    if session:
        session.close()
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy dbapi_cdc to Snowflake")
    parser.add_argument("--dry-run", action="store_true", help="Show SQL without executing")
    parser.add_argument("--config", default="config/replication_config.yaml", help="Path to config file")
    args = parser.parse_args()
    
    deploy(config_path=args.config, dry_run=args.dry_run)
