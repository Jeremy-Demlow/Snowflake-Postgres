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
docker compose up -d

# Access at http://localhost:3847
```

## Development

```bash
npm install
npm run dev
# http://localhost:3000
```

## Pages

- `/` - Home with quick stats
- `/setup` - Configuration (tables, WAL slots, setup guide)
- `/monitoring` - Real-time dashboard with sync trigger
- `/logs` - Forensic log viewer with filtering and CSV export
