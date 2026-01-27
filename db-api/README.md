# dbapi-cdc

Config-driven CDC replication from external databases to Snowflake using **Snowpark's native DB-API 2.0**.

## Features

- **Snowpark DB-API 2.0**: Uses `session.read.dbapi()` for efficient, parallelized extraction
- **Incremental CDC**: High watermark tracking via `updated_at` columns with timezone support
- **Task DAG Orchestration**: Parallel execution across tables with Snowflake Tasks
- **Multi-driver**: PostgreSQL (psycopg2), SQL Server (pymssql), MySQL (pymysql)
- **Auto-schema**: Creates target tables automatically from source
- **Sync Logging**: Event tracking with timing metrics in `_SYNC_LOGS` table
- **Monitoring Dashboard**: Streamlit app for real-time status

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
  host: "${PG_HOST}"  # Use env var or replace with your host
  port: 5432
  secret_name: "DBAPI_REPLICA_DB.PUBLIC.PG_SECRET"
  timezone: "UTC"  # Source DB timezone - critical for CDC accuracy
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

# Preview what will be deployed
SNOWFLAKE_CONNECTION_NAME=myconnection python -m dbapi_cdc.deploy_to_snowflake --dry-run

# Actually deploy
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

-- View sync logs with timing
SELECT LOG_TS, SOURCE_DB, TABLE_NAME, EVENT_TYPE, ROWS_AFFECTED, DURATION_MS
FROM DBAPI_REPLICA_DB.PUBLIC._SYNC_LOGS
ORDER BY LOG_TS DESC LIMIT 20;
```

### 5. Monitoring Dashboard

```bash
SNOWFLAKE_CONNECTION_NAME=myconnection streamlit run monitoring/streamlit_app.py
```

Features:
- Real-time sync status with row drift detection
- Source vs target row count comparison
- Task execution history
- One-click "Run Sync" and "Reconnect" buttons

## Example Results

**Full refresh of 260k rows in ~16 seconds:**

| SOURCE_DB | TABLE_NAME | ROWS | DURATION |
|-----------|------------|------|----------|
| customer_a_db | users | 63,579 | 14s |
| customer_a_db | orders | 43,000 | 16s |
| customer_a_db | payments | 33,000 | 14s |
| customer_a_db | products | 23,000 | 13s |
| customer_a_db | inventory | 23,000 | 16s |
| customer_b_db | (all 5) | 75,012 | 15s |

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

## How It Works

### The Key Innovation: Snowpark DB-API 2.0

Traditional ETL requires:
1. External compute (EC2, Lambda, etc.) to query source database
2. Staging data somewhere (S3, local disk)
3. Loading into Snowflake via COPY or Snowpipe

**Snowpark DB-API eliminates all of this.** With `session.read.dbapi()`, Snowflake's compute directly connects to your source database:

```python
# This runs INSIDE Snowflake - no external compute needed
df = session.read.dbapi(
    connection_factory,           # psycopg2.connect wrapper
    query="SELECT * FROM users WHERE updated_at > '2024-01-01'",
    fetch_size=100000,            # Batch size for streaming
    num_partitions=4,             # Parallel extraction threads
)
```

### Why This Works

1. **External Access Integration**: Snowflake securely connects to external hosts
   ```sql
   CREATE EXTERNAL ACCESS INTEGRATION PG_ACCESS_INTEGRATION
     ALLOWED_NETWORK_RULES = (PG_NETWORK_RULE)
     ALLOWED_AUTHENTICATION_SECRETS = (PG_SECRET)
     ENABLED = TRUE;
   ```

2. **Stored Procedure with Python Runtime**: The CDC logic runs as a stored procedure
   ```sql
   CREATE PROCEDURE SYNC_TABLE(config, database, table, full_refresh)
     LANGUAGE PYTHON
     RUNTIME_VERSION = '3.10'
     PACKAGES = ('snowflake-snowpark-python', 'pyyaml', 'psycopg2')
     IMPORTS = ('@CDC_STAGE/dbapi_cdc.zip')
     EXTERNAL_ACCESS_INTEGRATIONS = (PG_ACCESS_INTEGRATION)
     SECRETS = ('creds' = PG_SECRET)
     HANDLER = 'dbapi_cdc.procedures.sync_table'
   ```

3. **Task DAG for Parallelism**: Root task triggers child tasks that run in parallel
   ```
   DBAPI_REPLICATION_DAG (root, scheduled)
       ├── DBAPI_REPLICATION_DAG_CUSTOMER_A_DB_USERS
       ├── DBAPI_REPLICATION_DAG_CUSTOMER_A_DB_ORDERS
       ├── DBAPI_REPLICATION_DAG_CUSTOMER_A_DB_PAYMENTS
       └── ... (all run in parallel after root completes)
   ```

### Data Flow Detail

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SNOWFLAKE COMPUTE                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Stored Procedure: SYNC_TABLE                                    │   │
│  │                                                                  │   │
│  │  1. Get high watermark from _REPLICATION_STATE                   │   │
│  │     SELECT last_sync_value WHERE table='users'                   │   │
│  │     → '2024-01-23 10:00:00'                                      │   │
│  │                                                                  │   │
│  │  2. Extract via DB-API (runs inside Snowflake!)                  │   │
│  │     session.read.dbapi(                                          │   │
│  │       query="SELECT * FROM users WHERE updated_at > '...'",      │   │
│  │       num_partitions=4  # Parallel extraction                    │   │
│  │     ) ──────────────────────┐                                    │   │
│  │                             │                                    │   │
│  │  3. Load via MERGE         ▼                                    │   │
│  │     df.write.merge(     ┌──────────┐                            │   │
│  │       target_table,     │ Snowpark │                            │   │
│  │       primary_key,      │ DataFrame│                            │   │
│  │       update_cols       └──────────┘                            │   │
│  │     )                                                            │   │
│  │                                                                  │   │
│  │  4. Update watermark                                             │   │
│  │     UPDATE _REPLICATION_STATE SET last_sync_value = MAX(updated_at) │
│  │                                                                  │   │
│  │  5. Log event to _SYNC_LOGS                                      │   │
│  │     INSERT INTO _SYNC_LOGS (event_type='SYNC_COMPLETE', ...)     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              │ External Access Integration              │
│                              ▼                                          │
└─────────────────────────────────────────────────────────────────────────┘
                               │
                               │ TCP/5432 (allowed by Network Rule)
                               ▼
                    ┌─────────────────────┐
                    │     PostgreSQL      │
                    │  (external source)  │
                    └─────────────────────┘
```

### CDC High Watermark Strategy

Each table tracks its own watermark in `_REPLICATION_STATE`:

| source_db | table_name | last_sync_value | sync_status |
|-----------|------------|-----------------|-------------|
| customer_a_db | users | 2024-01-23 10:00:00 | completed |
| customer_a_db | orders | 2024-01-23 10:00:00 | completed |

**Incremental sync query:**
```sql
SELECT * FROM users WHERE updated_at > '2024-01-23 10:00:00'
```

**Timezone handling** (critical!): Source DB timezone must be configured to ensure watermark comparisons work correctly:
```yaml
source:
  timezone: "UTC"  # Must match your source database timezone
```

### MERGE Upsert Logic

Data is loaded using Snowpark's MERGE which handles both inserts and updates:

```python
df.write.mode("overwrite").merge(
    target_table,
    primary_key=["user_id"],           # Match on primary key
    update_columns=["name", "email", "updated_at"],  # Update these on match
)
```

This generates SQL like:
```sql
MERGE INTO target_table t
USING source_data s ON t.user_id = s.user_id
WHEN MATCHED THEN UPDATE SET t.name = s.name, t.email = s.email, ...
WHEN NOT MATCHED THEN INSERT (user_id, name, email, ...) VALUES (...)
```

## Modules

| Module | Purpose |
|--------|---------|
| `extractor.py` | Pull data via `session.read.dbapi()` with partitioned extraction |
| `loader.py` | Load into Snowflake via Snowpark MERGE |
| `replicator.py` | Orchestrate extraction, loading, and logging |
| `state.py` | Track high watermarks per table in `_REPLICATION_STATE` |
| `procedures.py` | Snowflake stored procedure entry points |
| `deploy_to_snowflake.py` | Deploy procedures, Task DAG, and upload package |

## Configuration

Key config options in `replication_config.yaml`:

| Option | Description |
|--------|-------------|
| `source.timezone` | Source DB timezone (UTC, America/Los_Angeles) - critical for CDC |
| `source.driver` | Database driver (psycopg2, pymssql, pymysql) |
| `orchestration.schedule` | Cron schedule for Task DAG |
| `orchestration.parallelism` | Number of parallel table syncs |

## Test Data Generation

```bash
# Generate test data (password via env var for security)
PG_PASSWORD=xxx python scripts/fast_data_gen.py --host your-host.com large

# Scale options: small, medium, large, xlarge
python scripts/fast_data_gen.py --help
```

## Testing

```bash
# Run unit tests
uv run pytest tests/ -v
```
