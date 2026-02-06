"""
dbapi_cdc.dag: Task DAG Deployment
==================================
Deploys the CDC sync DAG using Snowflake's native Python DAG API.

This module creates a Task DAG that schedules syncs for all tables
registered in TABLE_REGISTRY. Each table gets its own child task
that runs in parallel when the DAG is triggered.

Usage (Python):
    from snowflake.snowpark import Session
    from dbapi_cdc.dag import deploy_cdc_dag, DAGConfig
    
    session = Session.builder.config("connection_name", "myconnection").create()
    result = deploy_cdc_dag(session)

Usage (CLI):
    python -m dbapi_cdc.dag --connection myconnection
    python -m dbapi_cdc.dag --connection myconnection --dry-run
"""
from dataclasses import dataclass, field
from snowflake.snowpark import Session
from snowflake.core import Root
from snowflake.core._common import CreateMode
from snowflake.core.task import Cron
from snowflake.core.task.dagv1 import DAG, DAGTask, DAGOperation


@dataclass
class DAGConfig:
    """Configuration for the CDC sync DAG."""
    database: str = "DBAPI_REPLICA_DB"
    schema: str = "UTILS"
    dag_name: str = "CDC_SYNC_DAG"
    schedule: Cron = field(default_factory=lambda: Cron("*/15 * * * *", "America/Los_Angeles"))
    warehouse: str = "COMPUTE_WH"
    

def get_tables_from_registry(session: Session, config: DAGConfig) -> list[dict]:
    """Fetch all enabled tables from the registry."""
    df = session.table(f"{config.database}.{config.schema}.TABLE_REGISTRY").filter(
        "SYNC_ENABLED = TRUE"
    ).select(
        "TABLE_ID", 
        "DATABASE_ID", 
        "SOURCE_TABLE", 
        "TARGET_TABLE"
    )
    return [row.as_dict() for row in df.collect()]


def deploy_cdc_dag(
    session: Session, 
    config: DAGConfig | None = None,
    dry_run: bool = False
) -> dict:
    """
    Deploy the CDC sync DAG with one task per registered table.
    
    Args:
        session: Active Snowpark session
        config: DAG configuration (uses defaults if not provided)
        dry_run: If True, just print what would be created without deploying
        
    Returns:
        dict with deployment results including status, dag name, and task count
    """
    if config is None:
        config = DAGConfig()
    
    root = Root(session)
    schema = root.databases[config.database].schemas[config.schema]
    
    tables = get_tables_from_registry(session, config)
    
    if not tables:
        return {"status": "error", "message": "No enabled tables found in registry"}
    
    print(f"Found {len(tables)} enabled tables in registry")
    
    with DAG(
        config.dag_name,
        schedule=config.schedule,
        warehouse=config.warehouse,
        comment="CDC Sync DAG - syncs PostgreSQL tables to Snowflake via session.read.dbapi()"
    ) as dag:
        
        for table in tables:
            table_id = table["TABLE_ID"]
            database_id = table["DATABASE_ID"]
            source_table = table["SOURCE_TABLE"]
            target_table = table["TARGET_TABLE"]
            
            task_name = f"SYNC_{table_id.upper().replace('-', '_')}"
            
            DAGTask(
                task_name,
                f"CALL {config.database}.{config.schema}.SYNC_SINGLE_TABLE('{database_id}', '{table_id}')",
                warehouse=config.warehouse,
                comment=f"Sync {source_table} -> {target_table}"
            )
            
            if dry_run:
                print(f"  Would create task: {task_name}")
    
    if dry_run:
        print(f"\nDry run complete. Would create DAG '{config.dag_name}' with {len(tables)} tasks.")
        return {"status": "dry_run", "dag": config.dag_name, "task_count": len(tables)}
    
    dag_op = DAGOperation(schema)
    dag_op.deploy(dag, mode=CreateMode.or_replace)
    
    print(f"\nDeployed DAG '{config.dag_name}' with {len(tables)} tasks")
    print(f"To enable: ALTER TASK {config.database}.{config.schema}.{config.dag_name} RESUME")
    
    return {
        "status": "success",
        "dag": f"{config.database}.{config.schema}.{config.dag_name}",
        "task_count": len(tables),
        "tasks": [f"SYNC_{t['TABLE_ID'].upper().replace('-', '_')}" for t in tables]
    }


def drop_cdc_dag(session: Session, config: DAGConfig | None = None) -> dict:
    """
    Drop the CDC sync DAG and all its child tasks.
    
    Args:
        session: Active Snowpark session
        config: DAG configuration (uses defaults if not provided)
        
    Returns:
        dict with status
    """
    if config is None:
        config = DAGConfig()
    
    root = Root(session)
    schema = root.databases[config.database].schemas[config.schema]
    dag_op = DAGOperation(schema)
    
    try:
        dag_op.delete(config.dag_name)
        print(f"Dropped DAG '{config.dag_name}' and all child tasks")
        return {"status": "success", "message": f"Dropped {config.dag_name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy CDC Sync DAG")
    parser.add_argument("--connection", "-c", default="myconnection", help="Snowflake connection name")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Show what would be created without deploying")
    parser.add_argument("--drop", action="store_true", help="Drop the DAG instead of deploying")
    parser.add_argument("--database", default="DBAPI_REPLICA_DB", help="Target database")
    parser.add_argument("--schema", default="UTILS", help="Target schema")
    parser.add_argument("--warehouse", default="COMPUTE_WH", help="Warehouse for task execution")
    args = parser.parse_args()
    
    session = Session.builder.config("connection_name", args.connection).create()
    
    config = DAGConfig(
        database=args.database,
        schema=args.schema,
        warehouse=args.warehouse
    )
    
    try:
        if args.drop:
            result = drop_cdc_dag(session, config)
        else:
            result = deploy_cdc_dag(session, config, dry_run=args.dry_run)
        print(f"\nResult: {result}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
