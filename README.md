# Snowflake-Postgres CDC Replication

Config-driven CDC replication from PostgreSQL to Snowflake using **Snowpark's native DB-API 2.0**.

## Results

**220,591 rows replicated across 10 tables in ~45 seconds** (parallel execution)

| Database | Table | Rows |
|----------|-------|------|
| customer_a_db | users | 55,579 |
| customer_a_db | orders | 35,000 |
| customer_a_db | payments | 25,000 |
| customer_a_db | products | 15,000 |
| customer_a_db | inventory | 15,000 |
| customer_b_db | users | 15,012 |
| customer_b_db | orders | 15,000 |
| customer_b_db | payments | 15,000 |
| customer_b_db | products | 15,000 |
| customer_b_db | inventory | 15,000 |

## Quick Start

```bash
cd db-api
pip install -e .

# Deploy stored procedures + Task DAG
SNOWFLAKE_CONNECTION_NAME=myconnection python -m dbapi_cdc.deploy_to_snowflake

# Trigger sync
# EXECUTE TASK DBAPI_REPLICA_DB.UTILS.DBAPI_REPLICATION_DAG;
```

See [db-api/README.md](db-api/README.md) for full documentation.

## Architecture

```
PostgreSQL ──► Snowpark DB-API ──► Snowflake Tables
              session.read.dbapi()   MERGE upsert
                     │
                     ▼
              Task DAG (parallel)
              ├── users_task
              ├── orders_task
              ├── payments_task
              ├── products_task
              └── inventory_task
```

## Features

- **Snowpark DB-API 2.0**: Native `session.read.dbapi()` extraction
- **CDC via High Watermark**: Incremental sync using `updated_at`
- **Task DAG**: Parallel sync with Snowflake Tasks
- **Auto-Schema**: Creates target tables automatically
- **Multi-Database**: PostgreSQL, SQL Server, MySQL

## Project Structure

```
db-api/
├── dbapi_cdc/          # Core package
│   ├── extractor.py    # Snowpark DB-API extraction
│   ├── loader.py       # MERGE upsert loading
│   ├── replicator.py   # Orchestration
│   ├── state.py        # Watermark tracking
│   └── deploy_to_snowflake.py
├── config/             # YAML configs
└── tests/              # Unit tests
```
