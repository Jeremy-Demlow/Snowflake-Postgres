# PostgreSQL → Snowflake CDC Pipeline

**Production-ready Change Data Capture pipeline replicating PostgreSQL to Snowflake using Snowpark's `session.read.dbapi()`.**

## Quick Start

```bash
# 1. Infrastructure
cd terraform && terraform apply -auto-approve && cd ..

# 2. Deploy (procedures, WAL slots, config, task DAG)
python deploy.py -c myconnection --pg-password "$PG_PASSWORD"

# 3. Sync
EXECUTE TASK DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG;
```

## Architecture

```
PostgreSQL                          Snowflake
┌────────────────────┐              ┌─────────────────────────────────┐
│ customer_a_db      │──┐           │ DBAPI_REPLICA_DB                │
│ customer_b_db      │──┼──dbapi()─▶│ ├─ CUSTOMER_A_DATA (14 tables) │
│ customer_c_db      │──┘           │ ├─ CUSTOMER_B_DATA (14 tables) │
└────────────────────┘              │ └─ CUSTOMER_C_DATA (14 tables) │
     WAL Slots                      └─────────────────────────────────┘
  sf_cdc_customer_a                         Task DAG
  sf_cdc_customer_b                   CDC_SYNC_DAG (root)
  sf_cdc_customer_c                      └─ 42 parallel child tasks
```

## Sync Methods

| Method | Use Case | How It Works |
|--------|----------|--------------|
| **FULL** | Small reference tables | Truncate & reload entire table |
| **CDC** | Tables with timestamp column | Watermark-based MERGE (only rows > last sync) |
| **WAL** | Large tables, need DELETEs | PostgreSQL logical replication slot |

## Performance (Measured)

| Table Size | Throughput |
|------------|------------|
| 3M rows (rec_items) | **14,416 rows/sec** |
| 1.7M rows (rec_period_information) | **7,094 rows/sec** |
| 183K rows (var_activity) | **7,359 rows/sec** |

### 6M Row Projection

| Rows | Estimated Time |
|------|----------------|
| 6,000,000 | **7-14 minutes** per table |
| 18,000,000 (parallel DAG) | **~15-20 minutes** total |

## Project Structure

```
db-api/
├── deploy.py              # One-command deployment script
├── config/
│   └── replication_config.yaml  # Database and table definitions
├── dbapi_cdc/
│   ├── procedures.py      # Snowpark stored procedures
│   └── dag.py             # Task DAG deployment
├── terraform/
│   └── main.tf            # Infrastructure (DB, secrets, integrations)
└── scripts/
    └── demo.sh            # Demo/test script
```

## Configuration

Edit `config/replication_config.yaml`:

```yaml
databases:
  - database_id: "customer_a_prod"
    source_db_name: "customer_a_db"
    host: "your-pg-host.snowflake.app"
    target_schema: "CUSTOMER_A_DATA"
    wal_slot: "sf_cdc_customer_a"

defaults:
  sync_method: "full"
  primary_key: "pkid"

tables:
  - name: "users"
    sync_method: "wal"      # Use WAL for large tables
  - name: "rec_currency_rates_rt"
    sync_method: "cdc"      # Use CDC with timestamp watermark
    cdc_column: "db_update_date"
  - name: "os_currencies"   # Uses default: full
```

## Stored Procedures

| Procedure | Description |
|-----------|-------------|
| `SYNC_SINGLE_TABLE(db_id, table_id)` | Sync one table |
| `CHECK_PG_HEALTH()` | Test PostgreSQL connection |
| `SETUP_REPLICATION(config_json)` | Load config into registries |
| `CONSOLIDATE_SYNC_LOG()` | Merge sync results into registry |

## Troubleshooting

```sql
-- Check sync status
SELECT TABLE_ID, SYNC_METHOD, LAST_SYNC_STATUS, LAST_SYNC_RECORDS
FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
WHERE LAST_SYNC_STATUS != 'success';

-- Test PostgreSQL connection
CALL DBAPI_REPLICA_DB.UTILS.CHECK_PG_HEALTH();

-- Manual sync
CALL DBAPI_REPLICA_DB.UTILS.SYNC_SINGLE_TABLE('customer_a_prod', 'customer_a_prod_users');

-- Check task history
SELECT NAME, STATE, SCHEDULED_TIME, ERROR_MESSAGE
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY())
WHERE NAME LIKE '%SYNC%'
ORDER BY SCHEDULED_TIME DESC LIMIT 10;
```

## Requirements

- Snowflake account with External Access Integration capability
- PostgreSQL 14+ with logical replication enabled (`wal_level = logical`)
- Python 3.11+
- Snow CLI

## Key Files

- **deploy.py**: Main deployment script (procedures, WAL slots, config, DAG)
- **dbapi_cdc/procedures.py**: All sync logic (FULL, CDC, WAL methods)
- **dbapi_cdc/dag.py**: Task DAG creation using `snowflake.core.task.dagv1`
- **terraform/main.tf**: Infrastructure (database, schemas, secrets, integration)
- **config/replication_config.yaml**: Table and database definitions
