# CDC Monitor

React-based management console for PostgreSQL to Snowflake CDC pipeline.

## Features

- **Setup Wizard**: Configure databases, tables, WAL slots, sync methods
- **Monitoring Dashboard**: Real-time sync status, throughput, trigger syncs
- **Forensic Logs**: Full sync history with filtering, error analysis, CSV export

## Quick Start (Docker)

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your Snowflake/PostgreSQL credentials

# Start on port 3847
docker-compose up -d

# Access at http://localhost:3847
```

## Development

```bash
npm install
npm run dev
# http://localhost:3000
```

## Architecture

```
/                   # Home - quick stats and navigation
/setup              # Configuration wizard
  - Tables tab      # View/edit table sync config
  - WAL Slots tab   # Manage PostgreSQL replication slots
  - Guide tab       # Step-by-step setup instructions
/monitoring         # Real-time dashboard
  - Success/error counts
  - Trigger sync button
  - Auto-refresh every 5s
/logs               # Forensic log viewer
  - Filter by status/table
  - Detailed error analysis
  - CSV export
```

## API Endpoints

- `GET /api/health` - Health check
- `GET /api/sync-logs` - Fetch sync logs (params: limit, status, table)
- `GET /api/tables` - Get table configuration
- `POST /api/trigger-sync` - Execute CDC_SYNC_DAG task
