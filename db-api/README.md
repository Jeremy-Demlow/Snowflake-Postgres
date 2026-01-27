# dbapi-cdc

Config-driven CDC replication from external databases to Snowflake using **Snowpark's native DB-API 2.0**.

## Features

- **Snowpark DB-API 2.0**: Uses `session.read.dbapi()` for efficient, parallelized extraction
- **Incremental CDC**: High watermark tracking via `updated_at` columns
- **Task DAG Orchestration**: Parallel execution across tables with Snowflake Tasks
- **Multi-driver**: PostgreSQL (psycopg2), SQL Server (pymssql), MySQL (pymysql)
- **Auto-schema**: Creates target tables automatically from source

## Quick Start

### 1. Prerequisites - Set up Snowflake access

```sql
-- Create database
CREATE DATABASE DBAPI_REPLICA_DB;

-- Create secret for source credentials
CREATE SECRET DBAPI_REPLICA_DB.PUBLIC.PG_SECRET
  TYPE = PASSWORD
  USERNAME = 'your_user'
  PASSWORD = 'your_password';

-- Create network rule
CREATE NETWORK RULE DBAPI_REPLICA_DB.PUBLIC.PG_NETWORK_RULE
  TYPE = HOST_PORT
  MODE = EGRESS
  VALUE_LIST = ('your-postgres-host.example.com:5432');

-- Create external access integration
CREATE EXTERNAL ACCESS INTEGRATION PG_ACCESS_INTEGRATION
  ALLOWED_NETWORK_RULES = (DBAPI_REPLICA_DB.PUBLIC.PG_NETWORK_RULE)
  ALLOWED_AUTHENTICATION_SECRETS = (DBAPI_REPLICA_DB.PUBLIC.PG_SECRET)
  ENABLED = TRUE;
```

### 2. Configure replication

```yaml
# config/replication_config.yaml
source:
  driver: psycopg2
  host: "your-postgres-host.example.com"
  port: 5432
  secret_name: "DBAPI_REPLICA_DB.PUBLIC.PG_SECRET"
  databases:
    - name: customer_a_db
      tables:
        - name: users
          primary_key: [user_id]
          cdc_column: updated_at
        - name: orders
          primary_key: [id]
          cdc_column: updated_at

target:
  database: DBAPI_REPLICA_DB
  schema_pattern: "{source_db}_RAW"

orchestration:
  external_access_integration: PG_ACCESS_INTEGRATION
  dag_name: DBAPI_REPLICATION_DAG
  schedule: "0 */4 * * *"  # Every 4 hours
```

### 3. Deploy to Snowflake

```bash
pip install -e .
SNOWFLAKE_CONNECTION_NAME=myconnection python -m dbapi_cdc.deploy_to_snowflake
```

**Output:**
```
[1/5] Creating DBAPI_REPLICA_DB.UTILS and stage...
[2/5] Creating and uploading package...
[3/5] Creating SYNC_TABLE procedure...
[4/5] Creating SYNC_ALL procedure...
[5/5] Creating Task DAG...

============================================================
DEPLOYMENT COMPLETE!
============================================================

Procedures:
  - DBAPI_REPLICA_DB.UTILS.SYNC_TABLE(config, db, table, full_refresh)
  - DBAPI_REPLICA_DB.UTILS.SYNC_ALL(config, full_refresh)

Task DAG: DBAPI_REPLICA_DB.UTILS.DBAPI_REPLICATION_DAG
  Schedule: 0 */4 * * * (every 4 hours)
  Child Tasks: 10
```

### 4. Run and Monitor

```sql
-- Trigger immediate sync
EXECUTE TASK DBAPI_REPLICA_DB.UTILS.DBAPI_REPLICATION_DAG;

-- Check replication status
SELECT SOURCE_DB, TABLE_NAME, SYNC_STATUS, ROWS_SYNCED
FROM DBAPI_REPLICA_DB.PUBLIC._REPLICATION_STATE;

-- View task execution history
SELECT NAME, STATE, 
       TIMESTAMPDIFF('second', SCHEDULED_TIME, COMPLETED_TIME) as DURATION_SEC
FROM TABLE(DBAPI_REPLICA_DB.INFORMATION_SCHEMA.TASK_HISTORY())
WHERE NAME LIKE 'DBAPI_REPLICATION%'
ORDER BY SCHEDULED_TIME DESC;
```

## Example Results

**Replication State:**
| SOURCE_DB | TABLE_NAME | SYNC_STATUS | ROWS_SYNCED |
|-----------|------------|-------------|-------------|
| customer_a_db | users | completed | 55,579 |
| customer_a_db | orders | completed | 35,000 |
| customer_b_db | users | completed | 15,012 |
| customer_b_db | orders | completed | 15,000 |

**Task Execution (parallel):**
| Task | Duration |
|------|----------|
| DBAPI_REPLICATION_DAG (root) | 1s |
| customer_a_db.users | 37s |
| customer_a_db.orders | 42s |
| customer_b_db.users | 43s |
| customer_b_db.orders | 45s |

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  PostgreSQL     │────▶│  Snowpark DB-API     │────▶│  Snowflake      │
│  (source)       │     │  session.read.dbapi()│     │  MERGE upsert   │
└─────────────────┘     └──────────────────────┘     └─────────────────┘
                                  │
                        ┌─────────┴─────────┐
                        │    Task DAG       │
                        │  (parallel sync)  │
                        │                   │
                        │  ┌─────┐ ┌─────┐  │
                        │  │users│ │orders│ │
                        │  └─────┘ └─────┘  │
                        │  ┌─────┐ ┌─────┐  │
                        │  │prod │ │inv  │  │
                        │  └─────┘ └─────┘  │
                        └───────────────────┘
```

## Modules

| Module | Purpose |
|--------|---------|
| `extractor.py` | Pull data via `session.read.dbapi()` |
| `loader.py` | Load into Snowflake via Snowpark MERGE |
| `replicator.py` | Orchestrate extraction and loading |
| `state.py` | Track high watermarks per table |
| `procedures.py` | Snowflake stored procedure handlers |
| `deploy_to_snowflake.py` | Deploy procedures and Task DAG |

## How It Works

1. **Extraction**: Uses Snowpark's `session.read.dbapi()` to connect to PostgreSQL via psycopg2 driver
2. **CDC**: Tracks high watermark (`updated_at`) to only pull changed rows
3. **Loading**: Uses Snowpark MERGE for upserts based on primary key
4. **Scheduling**: Task DAG runs child tasks in parallel on schedule

## Testing

```bash
# Run unit tests
uv run pytest tests/ -v
```
