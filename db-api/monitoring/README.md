# CDC Pipeline Monitor

Streamlit dashboard for monitoring the DB-API CDC replication pipeline.

## Features

- **Health Status** - At-a-glance pipeline health (green/yellow/red)
- **KPI Metrics** - Total rows, tables, failures, avg duration
- **Table Status** - Per-table sync status with freshness indicators
- **Task History** - 24-hour execution history with success/fail chart
- **Manual Trigger** - Button to run sync on-demand
- **Error Log** - Recent failures with error messages

## Quick Start

### Local Development

```bash
# Set connection name
export SNOWFLAKE_CONNECTION_NAME=myconnection

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run streamlit_app.py
```

Open http://localhost:8501

### Docker

```bash
# Build image
docker build -t cdc-monitor .

# Run container (mount your Snowflake config)
docker run -p 8501:8501 \
  -v ~/.snowflake:/root/.snowflake:ro \
  -e SNOWFLAKE_CONNECTION_NAME=myconnection \
  cdc-monitor
```

## Configuration

The app connects to Snowflake using the connection name specified in `SNOWFLAKE_CONNECTION_NAME`. 

Ensure your `~/.snowflake/connections.toml` has the connection configured:

```toml
[myconnection]
account = "your_account"
user = "your_user"
authenticator = "externalbrowser"  # or password, etc.
```

## Data Sources

The dashboard queries:
- `DBAPI_REPLICA_DB.PUBLIC._REPLICATION_STATE` - Sync status per table
- `DBAPI_REPLICA_DB.INFORMATION_SCHEMA.TASK_HISTORY()` - Task execution history

## Screenshot

```
┌─────────────────────────────────────────────────────────┐
│  🔄 CDC Pipeline Monitor                    [Sync Now]  │
├─────────────────────────────────────────────────────────┤
│  🟢 Pipeline Status: Healthy                            │
│  All systems operational                                │
├─────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ 220,591  │  │   10     │  │    0     │  │   30s   │ │
│  │Total Rows│  │ Tables   │  │ Failures │  │Avg Sync │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
├─────────────────────────────────────────────────────────┤
│  📊 Table Status              │  📈 Task Executions     │
│  ┌─────────┬────────┬─────┐  │                         │
│  │ Table   │ Status │Rows │  │  ████████████  45       │
│  │ users   │ ✅     │55K  │  │  ✅ 45 succeeded        │
│  │ orders  │ ✅     │35K  │  │  ❌ 0 failed            │
│  └─────────┴────────┴─────┘  │                         │
└─────────────────────────────────────────────────────────┘
```
