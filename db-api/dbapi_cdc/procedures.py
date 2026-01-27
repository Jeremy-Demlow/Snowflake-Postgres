"""
Snowflake stored procedure entry points.

These handlers are deployed as Snowflake stored procedures.
"""

from snowflake.snowpark import Session


def _parse_config(config_yaml: str):
    """Parse YAML config into ReplicationConfig."""
    import yaml

    from .replicator import DatabaseConfig, ReplicationConfig, TableConfig

    raw = yaml.safe_load(config_yaml)

    databases = [
        DatabaseConfig(
            name=db["name"],
            tables=[
                TableConfig(
                    name=t["name"],
                    primary_key=t["primary_key"],
                    cdc_column=t.get("cdc_column"),
                )
                for t in db["tables"]
            ],
        )
        for db in raw["source"]["databases"]
    ]

    return ReplicationConfig(
        source_host=raw["source"]["host"],
        source_port=raw["source"]["port"],
        source_secret_name=raw["source"]["secret_name"],
        databases=databases,
        target_database=raw["target"]["database"],
        target_schema_pattern=raw["target"]["schema_pattern"],
        driver=raw["source"].get("driver", "psycopg2"),
        fetch_size=raw.get("extraction", {}).get("fetch_size", 50_000),
        batch_size=raw.get("extraction", {}).get("batch_size", 100_000),
    )


def sync_table(
    session: Session,
    config_yaml: str,
    source_database: str,
    table_name: str,
    full_refresh: bool = False,
) -> str:
    """Sync a single table from external database to Snowflake."""
    from .replicator import Replicator

    config = _parse_config(config_yaml)
    replicator = Replicator(session, config)

    db_config = next((d for d in config.databases if d.name == source_database), None)
    if not db_config:
        return f"ERROR: Database {source_database} not found in config"

    table_config = next((t for t in db_config.tables if t.name == table_name), None)
    if not table_config:
        return f"ERROR: Table {table_name} not found in database {source_database}"

    result = replicator.sync_table(source_database, table_config, full_refresh)

    if result["status"] == "success":
        return f"SUCCESS: Synced {result.get('rows', 0)} rows to {source_database}.{table_name}"
    return f"FAILED: {result.get('error', 'Unknown error')}"


def sync_all(
    session: Session,
    config_yaml: str,
    full_refresh: bool = False,
) -> str:
    """Sync all tables defined in config."""
    from .replicator import Replicator

    config = _parse_config(config_yaml)
    replicator = Replicator(session, config)
    results = replicator.sync_all(full_refresh)

    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    total_rows = sum(r.get("rows", 0) for r in results if r["status"] == "success")

    details = [
        f"{r['database']}.{r['table']}: {'OK' if r['status'] == 'success' else 'FAIL'}"
        for r in results
    ]

    return f"Completed: {success} succeeded, {failed} failed, {total_rows} rows\n" + "\n".join(details)
