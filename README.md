# Snowflake-Postgres CDC Replication

Config-driven CDC replication from PostgreSQL to Snowflake using **Snowpark's native DB-API 2.0**.

## Results

**260k+ rows replicated across 10 tables in ~16 seconds** (parallel execution)

| Database | Table | Rows |
|----------|-------|------|
| customer_a_db | users | 63,579 |
| customer_a_db | orders | 43,000 |
| customer_a_db | payments | 33,000 |
| customer_a_db | products | 23,000 |
| customer_a_db | inventory | 23,000 |
| customer_b_db | users | 15,012 |
| customer_b_db | orders | 15,000 |
| customer_b_db | payments | 15,000 |
| customer_b_db | products | 15,000 |
| customer_b_db | inventory | 15,000 |

## Quick Start

```bash
cd db-api
pip install -e .

# Preview deployment (dry-run)
SNOWFLAKE_CONNECTION_NAME=myconnection python -m dbapi_cdc.deploy_to_snowflake --dry-run

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
- **CDC via High Watermark**: Incremental sync using `updated_at` with timezone support
- **Task DAG**: Parallel sync with Snowflake Tasks
- **Auto-Schema**: Creates target tables automatically
- **Multi-Database**: PostgreSQL, SQL Server, MySQL
- **Monitoring Dashboard**: Streamlit app for real-time sync status
- **Sync Logging**: Event tracking with timing metrics

## Monitoring

```bash
# Start the monitoring dashboard
cd db-api
SNOWFLAKE_CONNECTION_NAME=myconnection streamlit run monitoring/streamlit_app.py
```

Dashboard features:
- Real-time sync status with row drift detection
- Source vs target comparison
- Task execution history
- One-click sync trigger and reconnect

## Project Structure

```
db-api/
├── dbapi_cdc/           # Core CDC package
│   ├── extractor.py     # Snowpark DB-API extraction
│   ├── loader.py        # MERGE upsert loading
│   ├── replicator.py    # Orchestration + logging
│   ├── state.py         # Watermark tracking
│   └── deploy_to_snowflake.py
├── monitoring/          # Streamlit dashboard
├── config/              # YAML configs
├── scripts/             # Test data generation
└── tests/               # Unit tests
```

## Environment Variables

```bash
# Required for deployment
SNOWFLAKE_CONNECTION_NAME=myconnection

# Required for test data scripts
PG_HOST=your-postgres-host.example.com
PG_PASSWORD=your_password
PG_USER=snowflake_admin  # optional, defaults to snowflake_admin
```
