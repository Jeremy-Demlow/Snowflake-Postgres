# Architecture & Design

## Overview

This CDC pipeline replicates data from PostgreSQL to Snowflake using three sync methods, orchestrated by a Snowflake Task DAG.

## Components

### 1. Infrastructure (Terraform)

```
terraform/main.tf
├── DBAPI_REPLICA_DB (database)
├── UTILS schema (procedures, registries)
├── PUBLIC schema (secrets, network rules)
├── PG_SECRET (PostgreSQL credentials)
├── PG_NETWORK_RULE (egress to PostgreSQL host)
├── PG_ACCESS_INTEGRATION (external access)
├── DATABASE_REGISTRY table
├── TABLE_REGISTRY table
└── SYNC_LOG table
```

### 2. Application (deploy.py)

The deployment script performs:
1. **Snowpark Deploy**: Uploads `procedures.py` and creates stored procedures
2. **WAL Slot Creation**: Creates replication slots in each PostgreSQL database
3. **Config Load**: Calls `SETUP_REPLICATION()` to populate registries
4. **Schema Creation**: Creates target schemas (CUSTOMER_A_DATA, etc.)
5. **Task DAG**: Creates root task + 42 child tasks + consolidation task

### 3. Sync Methods

#### FULL Sync
```
PostgreSQL                    Snowflake
┌──────────┐                  ┌──────────┐
│  Table   │ ──SELECT *──────▶│  Table   │ (OVERWRITE)
└──────────┘                  └──────────┘
```
- Reloads entire table every sync
- Best for small reference tables (<100K rows)
- Simple, reliable, no state tracking

#### CDC Sync (Watermark)
```
PostgreSQL                    Snowflake
┌──────────┐                  ┌──────────┐
│  Table   │ ──WHERE ts > ?──▶│  MERGE   │
└──────────┘                  └──────────┘
       ▲                            │
       └────── watermark ◀──────────┘
```
- Uses timestamp column (e.g., `db_update_date`)
- Only syncs rows newer than last watermark
- Requires MERGE for upserts

#### WAL Sync (Logical Replication)
```
PostgreSQL                    Snowflake
┌──────────┐                  ┌──────────┐
│  WAL     │ ──peek_changes──▶│  MERGE   │ (inserts/updates)
│  Slot    │                  │  DELETE  │ (deletes)
└──────────┘                  └──────────┘
       │
       └─── consume after sync
```
- Captures INSERT, UPDATE, DELETE operations
- Uses PostgreSQL logical replication slots
- Only way to capture deletes
- Requires `wal_level = logical` in PostgreSQL

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         Task DAG                                 │
│  CDC_SYNC_DAG (root, every 15 min)                              │
│       │                                                          │
│       ├── TASK_CUSTOMER_A_PROD_USERS (WAL)                      │
│       ├── TASK_CUSTOMER_A_PROD_REC_ITEMS (WAL)                  │
│       ├── TASK_CUSTOMER_A_PROD_REC_CURRENCY_RATES_RT (CDC)      │
│       ├── TASK_CUSTOMER_A_PROD_OS_CURRENCIES (FULL)             │
│       ├── ... (38 more parallel tasks)                          │
│       │                                                          │
│       └── TASK_CONSOLIDATE_SYNC_LOG (runs AFTER all above)      │
└─────────────────────────────────────────────────────────────────┘
```

## Lock-Free Parallel Execution

Problem: 42 tasks updating TABLE_REGISTRY simultaneously causes lock contention.

Solution: **SYNC_LOG pattern**
1. Each task INSERTs results to SYNC_LOG (append-only, no locks)
2. Consolidation task runs AFTER all syncs complete
3. Single MERGE updates TABLE_REGISTRY from SYNC_LOG
4. TRUNCATE clears SYNC_LOG

```sql
-- Each parallel task does this (no lock contention):
INSERT INTO SYNC_LOG (TABLE_ID, SYNC_STATUS, SYNC_RECORDS, ...)
VALUES ('customer_a_prod_users', 'success', 10000, ...);

-- Consolidation task does this (single writer):
MERGE INTO TABLE_REGISTRY USING SYNC_LOG ...
```

## Registry Schema

### DATABASE_REGISTRY
| Column | Description |
|--------|-------------|
| DATABASE_ID | Unique identifier (e.g., `customer_a_prod`) |
| SOURCE_DB_NAME | PostgreSQL database name |
| HOST | PostgreSQL host |
| TARGET_SCHEMA | Snowflake schema for this database's tables |
| SOURCE_SCHEMA | PostgreSQL schema (usually `data` or `public`) |

### TABLE_REGISTRY
| Column | Description |
|--------|-------------|
| TABLE_ID | Unique identifier (e.g., `customer_a_prod_users`) |
| DATABASE_ID | FK to DATABASE_REGISTRY |
| SYNC_METHOD | `full`, `cdc`, or `wal` |
| PRIMARY_KEY_COLUMN | Column(s) for MERGE (comma-separated for composite) |
| CDC_COLUMN | Timestamp column for CDC method |
| WAL_SLOT_NAME | PostgreSQL replication slot name |
| LAST_WATERMARK | Last CDC watermark value |
| LAST_SYNC_STATUS | `success` or error message |
| LAST_SYNC_RECORDS | Rows synced in last run |

## Performance Characteristics

| Scenario | Throughput | Notes |
|----------|------------|-------|
| Large table FULL (3M rows) | 14,400 rows/sec | Limited by PostgreSQL read |
| Medium table FULL (1.7M rows) | 7,000 rows/sec | |
| CDC incremental | 1,600 rows/sec | Only changed rows |
| WAL incremental | 2,300 rows/sec | Only changed rows |

Parallel execution means 42 tables sync simultaneously, so total time ≈ slowest single table.
