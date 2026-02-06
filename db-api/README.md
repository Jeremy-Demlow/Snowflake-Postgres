# PostgreSQL to Snowflake CDC Pipeline

A production-grade Change Data Capture (CDC) pipeline that replicates data from PostgreSQL databases to Snowflake with support for multiple sync methods, real-time monitoring, and forensic logging.

> **Note**: This solution is nearly self-contained but requires external PostgreSQL database access and Snowflake account credentials to be configured.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CDC MONITOR (React/Next.js)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   Dashboard  │  │    Setup     │  │  Monitoring  │  │   Forensic Logs      │ │
│  │  • Stats     │  │  • Tables    │  │  • Syncs     │  │  • Search/Filter     │ │
│  │  • Quick Nav │  │  • WAL Slots │  │  • Status    │  │  • Log Details       │ │
│  │              │  │  • Guide     │  │  • Charts    │  │  • Export CSV        │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             SNOWFLAKE (Data Platform)                           │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          DBAPI_REPLICA_DB.UTILS                         │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────────┐ │   │
│  │  │ DATABASE_      │  │ TABLE_         │  │ SYNC_LOG                   │ │   │
│  │  │ REGISTRY       │  │ REGISTRY       │  │ (Forensic Audit Trail)     │ │   │
│  │  │ • DB configs   │  │ • Table meta   │  │ • Every sync execution     │ │   │
│  │  │ • Credentials  │  │ • Sync methods │  │ • Row counts & duration    │ │   │
│  │  │                │  │ • Watermarks   │  │ • CDC row details          │ │   │
│  │  └────────────────┘  └────────────────┘  └────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         STORED PROCEDURES                               │   │
│  │  • SYNC_SINGLE_TABLE    - Sync one table (full/cdc/wal)                │   │
│  │  • SYNC_ALL_TABLES      - Orchestrate all table syncs                  │   │
│  │  • CONSOLIDATE_SYNC_LOG - Move logs from TABLE_REGISTRY to SYNC_LOG    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                              TASK DAG                                   │   │
│  │          ┌─────────────────┐         ┌─────────────────────────┐       │   │
│  │          │ SYNC_ALL_TABLES │ ──────► │ CONSOLIDATE_SYNC_LOG    │       │   │
│  │          │ (Every 15 min)  │         │ (After sync completes)  │       │   │
│  │          └─────────────────┘         └─────────────────────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          POSTGRESQL DATABASES                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐              │
│  │  customer_a_prod │  │  customer_b_prod │  │  customer_c_prod │              │
│  │  (14 tables)     │  │  (14 tables)     │  │  (14 tables)     │              │
│  │                  │  │                  │  │                  │              │
│  │  WAL Slot:       │  │  WAL Slot:       │  │  WAL Slot:       │              │
│  │  sf_cdc_customer │  │  sf_cdc_customer │  │  sf_cdc_customer │              │
│  │  _a              │  │  _b              │  │  _c              │              │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Sync Methods

| Method | Description | Use Case | Performance |
|--------|-------------|----------|-------------|
| **FULL** | Truncate & reload entire table | Dimension tables, small tables | ~15K rows/sec |
| **CDC** | Incremental based on watermark column | Append-only or has `updated_at` | ~50K rows/sec |
| **WAL** | PostgreSQL logical replication | Real-time, high-frequency updates | Near real-time |

## UI Features

### Dashboard (`/`)
- **Pipeline Status Cards**: Shows 3 databases, 42 tables, sync health, 627K rows synced
- **Quick Navigation**: Cards linking to Setup, Monitoring, and Forensic Logs
- **Connection Status**: Real-time Snowflake connection indicator
- **Quick Actions**: "View Live Syncs" and "Check Logs" buttons

### Setup (`/setup`)
| Tab | Features |
|-----|----------|
| **Tables** | View all 42 tables with sync method badges (WAL/CDC/FULL), filter by database, see row counts |
| **WAL Slots** | PostgreSQL replication slot status, LSN positions, slot health |
| **Guide** | Step-by-step setup instructions with SQL snippets |

### Monitoring (`/monitoring`)
| Tab | Features |
|-----|----------|
| **Table Status** | Real-time sync status per table, last sync time, records synced, manual trigger buttons |
| **Charts** | Visual analytics - sync trends, rows per method, database distribution |

### Forensic Logs (`/logs`)
- **Search & Filter**: Filter by table, status, date range
- **Log Table**: Complete audit trail with LOG_ID, TABLE_ID, status, records, duration
- **Detail View**: Click any row to see full sync details including CDC rows and watermarks
- **Export**: Download filtered logs as CSV

## Performance Benchmarks

Based on actual sync operations:

| Metric | Value |
|--------|-------|
| **Total Tables Synced** | 42 |
| **Total Rows Synced** | 627,233 |
| **Average Rows/Table** | ~15,000 |
| **Largest Single Table** | 183,125 rows |
| **Databases Replicated** | 3 |

### Sync Method Distribution

| Method | Tables | Rows Synced |
|--------|--------|-------------|
| WAL (Logical Replication) | 21 | Real-time stream |
| FULL (Truncate + Reload) | 18 | 627,233 |
| CDC (Incremental) | 3 | Delta only |

## Project Structure

```
db-api/
├── cdc-monitor/              # React/Next.js monitoring app
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx      # Dashboard
│   │   │   ├── setup/        # Setup & Configuration
│   │   │   ├── monitoring/   # Real-time monitoring
│   │   │   ├── logs/         # Forensic logs
│   │   │   └── api/          # API routes
│   │   └── lib/
│   │       └── snowflake.ts  # Snowflake SDK connection
│   ├── package.json
│   └── next.config.js
│
├── deploy.py                 # Deployment script
├── terraform/                # Infrastructure as code
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
│
└── docs/
    └── screenshots/          # App screenshots
```

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.9+
- Snowflake account with ACCOUNTADMIN access
- PostgreSQL database(s) with logical replication enabled

### 1. Infrastructure Setup

```bash
cd terraform
terraform init
terraform apply -auto-approve
```

### 2. Deploy CDC Pipeline

```bash
python deploy.py -c myconnection --pg-password "$PG_PASSWORD"

# This creates:
# - Stored procedures for sync
# - WAL replication slots
# - TABLE_REGISTRY and DATABASE_REGISTRY
# - Task DAG for orchestration
```

### 3. Start the Monitor

```bash
cd cdc-monitor
npm install
npm run dev
```

Open http://localhost:3000

### 4. Configure Tables

1. Go to **Setup > Tables**
2. Review discovered tables from PostgreSQL
3. Set sync method per table (FULL/CDC/WAL)
4. Enable tables for sync

### 5. Run Sync

- **Manual**: Click "Trigger Sync" in Monitoring page
- **Scheduled**: Task DAG runs every 15 minutes automatically

## Environment Variables

Create `.env.local` in `cdc-monitor/`:

```env
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_DATABASE=DBAPI_REPLICA_DB
SNOWFLAKE_SCHEMA=UTILS
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_ROLE=ACCOUNTADMIN
```

Or use Snowflake connection name:

```env
SNOWFLAKE_CONNECTION_NAME=myconnection
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/stats` | Pipeline overview statistics |
| `GET /api/databases` | List configured databases |
| `GET /api/tables` | List tables with sync config |
| `GET /api/wal-slots` | PostgreSQL WAL slot status |
| `GET /api/sync-logs` | Forensic sync history |
| `GET /api/monitoring` | Real-time sync status |
| `POST /api/trigger-sync` | Manual sync trigger |

## Database Schema

### DATABASE_REGISTRY

```sql
CREATE TABLE DATABASE_REGISTRY (
    DATABASE_ID VARCHAR PRIMARY KEY,
    PG_HOST VARCHAR,
    PG_PORT INTEGER,
    PG_DATABASE VARCHAR,
    PG_USER VARCHAR,
    TARGET_DATABASE VARCHAR,
    TARGET_SCHEMA VARCHAR,
    SLOT_NAME VARCHAR,
    CREATED_AT TIMESTAMP_NTZ,
    UPDATED_AT TIMESTAMP_NTZ
);
```

### TABLE_REGISTRY

```sql
CREATE TABLE TABLE_REGISTRY (
    TABLE_ID VARCHAR PRIMARY KEY,
    DATABASE_ID VARCHAR REFERENCES DATABASE_REGISTRY,
    SOURCE_TABLE VARCHAR,
    TARGET_TABLE VARCHAR,
    SYNC_METHOD VARCHAR,      -- 'full', 'cdc', 'wal'
    SYNC_ENABLED BOOLEAN,
    WATERMARK_COLUMN VARCHAR, -- for CDC method
    LAST_WATERMARK_VALUE VARCHAR,
    LAST_SYNC_AT TIMESTAMP_NTZ,
    LAST_SYNC_STATUS VARCHAR,
    LAST_SYNC_RECORDS INTEGER
);
```

### SYNC_LOG

```sql
CREATE TABLE SYNC_LOG (
    LOG_ID INTEGER AUTOINCREMENT PRIMARY KEY,
    TABLE_ID VARCHAR,
    SYNC_STATUS VARCHAR,
    SYNC_RECORDS INTEGER,
    SYNC_DURATION_SEC FLOAT,
    NEW_WATERMARK VARCHAR,
    CDC_ROWS INTEGER,
    LOGGED_AT TIMESTAMP_NTZ
);
```

## Known Limitations

1. **Not Fully Self-Contained**: Requires external PostgreSQL databases and Snowflake credentials
2. **WAL Slots**: Must be created manually on PostgreSQL side (SQL provided in Setup Guide)
3. **Schema Changes**: DDL changes in PostgreSQL require manual table re-registration
4. **Large Tables**: FULL sync on very large tables (>10M rows) may timeout

## Future Enhancements

- [ ] Schema drift detection and auto-migration
- [ ] Parallel sync execution for faster throughput
- [ ] Alerting via Slack/email on sync failures
- [ ] Historical trend charts (week/month views)
- [ ] Support for additional source databases (MySQL, SQL Server)

## License

MIT
