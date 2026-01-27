"""
Replicator: Orchestrate CDC replication from external databases to Snowflake.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Optional
from zoneinfo import ZoneInfo

import yaml
from snowflake.snowpark import Session

from .extractor import ExtractionConfig, Extractor
from .loader import LoadConfig, Loader
from .state import StateManager

__all__ = ["Replicator", "ReplicationConfig", "load_config"]

log = logging.getLogger(__name__)


@dataclass
class TableConfig:
    name: str
    primary_key: list[str]
    cdc_column: Optional[str] = None


@dataclass
class DatabaseConfig:
    name: str
    tables: list[TableConfig]


LARGE_TABLE_THRESHOLD = 50_000


@dataclass
class ReplicationConfig:
    source_host: str
    source_port: int
    source_secret_name: str
    databases: list[DatabaseConfig]
    target_database: str
    target_schema_pattern: str
    driver: str = "psycopg2"
    fetch_size: int = 50_000
    batch_size: int = 100_000
    large_table_threshold: int = LARGE_TABLE_THRESHOLD
    num_partitions: int = 4
    source_timezone: str = "UTC"  # Source DB timezone for CDC watermarks


class Replicator:
    """Orchestrate CDC replication."""

    def __init__(self, session: Session, config: ReplicationConfig):
        self.session = session
        self.config = config
        self.state = StateManager(session, config.target_database)
        self.loader = Loader(session)

    def _log_event(self, source_db: str, table_name: str, event_type: str, 
                   message: str, rows_affected: int = None, duration_ms: int = None, metadata: dict = None):
        """Log a sync event to _SYNC_LOGS table."""
        try:
            meta_json = "NULL" if metadata is None else f"PARSE_JSON('{str(metadata).replace(chr(39), chr(39)+chr(39))}')"
            rows_val = "NULL" if rows_affected is None else str(rows_affected)
            dur_val = "NULL" if duration_ms is None else str(duration_ms)
            self.session.sql(f"""
                INSERT INTO {self.config.target_database}.PUBLIC._SYNC_LOGS 
                (SOURCE_DB, TABLE_NAME, EVENT_TYPE, MESSAGE, ROWS_AFFECTED, DURATION_MS, METADATA)
                VALUES ('{source_db}', '{table_name}', '{event_type}', '{message}', {rows_val}, {dur_val}, {meta_json})
            """).collect()
        except Exception as e:
            log.warning(f"Failed to log event: {e}")

    def _get_creds(self) -> tuple[str, str]:
        """Get database credentials from Snowflake secret or environment."""
        try:
            import _snowflake
            creds = _snowflake.get_username_password("creds")
            return creds.username, creds.password
        except (ImportError, Exception):
            pass

        user = os.getenv("PG_USER")
        password = os.getenv("PG_PASSWORD")
        if user and password:
            log.info("Using credentials from environment")
            return user, password

        raise ValueError("Secret 'creds' not bound and PG_USER/PG_PASSWORD not set")

    def _target_schema(self, source_db: str) -> str:
        return self.config.target_schema_pattern.format(source_db=source_db).upper()

    def sync_table(
        self,
        db_name: str,
        table: TableConfig,
        full_refresh: bool = False,
    ) -> dict[str, Any]:
        """Sync a single table."""
        schema = self._target_schema(db_name)
        log.info(f"Syncing {db_name}.{table.name} -> {schema}.{table.name}")
        
        sync_start = time.time()
        self._log_event(db_name, table.name, "SYNC_START", 
                       f"Starting {'full refresh' if full_refresh else 'incremental'} sync to {schema}.{table.name}")

        self.state.ensure_state_table()
        self.state.mark_running(db_name, table.name)

        try:
            user, password = self._get_creds()
            extractor = Extractor(
                self.session, self.config.source_host, self.config.source_port,
                user, password, self.config.driver,
            )

            ext_cfg = ExtractionConfig(
                host=self.config.source_host,
                port=self.config.source_port,
                database=db_name,
                table=table.name,
                primary_key=table.primary_key,
                driver=self.config.driver,
                cdc_column=table.cdc_column,
                fetch_size=self.config.fetch_size,
                num_partitions=self.config.num_partitions,
            )

            load_cfg = LoadConfig(
                target_database=self.config.target_database,
                target_schema=schema,
                target_table=table.name.upper(),
                primary_key=table.primary_key,
                cdc_column=table.cdc_column,
            )

            watermark = None
            if not full_refresh and table.cdc_column:
                watermark = self.state.get_high_watermark(db_name, table.name)
                if watermark:
                    log.info(f"Incremental from {watermark}")

            extract_start = time.time()
            source_count = extractor.get_count(ext_cfg)
            self._log_event(db_name, table.name, "SOURCE_COUNT", 
                           f"Source has {source_count:,} rows", rows_affected=source_count)
            
            if source_count > self.config.large_table_threshold:
                log.info(f"Large table ({source_count:,} rows), using partitioned extraction")
                self._log_event(db_name, table.name, "EXTRACT_START", 
                               f"Starting partitioned extraction ({self.config.num_partitions} partitions)")
                df = extractor.extract_partitioned(
                    ext_cfg,
                    watermark,
                    partition_column=table.primary_key[0],
                    lower_bound=0,
                    upper_bound=source_count + 10000,
                )
            else:
                self._log_event(db_name, table.name, "EXTRACT_START", "Starting single-threaded extraction")
                df = extractor.extract(ext_cfg, watermark)
            
            extract_ms = int((time.time() - extract_start) * 1000)
            self._log_event(db_name, table.name, "EXTRACT_COMPLETE", 
                           f"Extraction completed", duration_ms=extract_ms)
            load_start = time.time()
            load_type = "FULL" if full_refresh or not watermark else "MERGE"
            self._log_event(db_name, table.name, "LOAD_START", f"Starting {load_type} load to Snowflake")
            
            if full_refresh or not watermark:
                rows = self.loader.load_full(load_cfg, df)
            else:
                rows = self.loader.load_merge(load_cfg, df)
            
            load_ms = int((time.time() - load_start) * 1000)
            self._log_event(db_name, table.name, "LOAD_COMPLETE", 
                           f"{load_type} load completed with {rows:,} rows", 
                           rows_affected=rows, duration_ms=load_ms)

            new_wm = extractor.get_max_watermark(ext_cfg)
            if not new_wm:
                # Fallback: use current time in source timezone (critical for CDC accuracy)
                src_tz = ZoneInfo(self.config.source_timezone)
                new_wm = datetime.now(src_tz).replace(tzinfo=None)
            self.state.mark_completed(db_name, table.name, new_wm, rows)
            
            total_ms = int((time.time() - sync_start) * 1000)
            self._log_event(db_name, table.name, "SYNC_COMPLETE", 
                           f"Sync completed successfully: {rows:,} rows in {total_ms}ms",
                           rows_affected=rows, duration_ms=total_ms)

            log.info(f"Loaded {rows} rows")
            return {"status": "success", "database": db_name, "table": table.name, "rows": rows}

        except Exception as e:
            log.error(f"Failed: {e}")
            total_ms = int((time.time() - sync_start) * 1000)
            self._log_event(db_name, table.name, "SYNC_FAILED", 
                           f"Sync failed: {str(e)}", duration_ms=total_ms)
            self.state.mark_failed(db_name, table.name, str(e))
            return {"status": "failed", "database": db_name, "table": table.name, "error": str(e)}

    def sync_database(self, db: DatabaseConfig, full_refresh: bool = False) -> list[dict]:
        """Sync all tables in a database."""
        return [self.sync_table(db.name, t, full_refresh) for t in db.tables]

    def sync_all(self, full_refresh: bool = False) -> list[dict]:
        """Sync all configured databases."""
        results = []
        for db in self.config.databases:
            results.extend(self.sync_database(db, full_refresh))
        return results

    def status(self) -> list[dict]:
        """Get replication status for all tables."""
        self.state.ensure_state_table()
        return [
            {
                "source_db": s.source_db,
                "table": s.table_name,
                "watermark": str(s.last_sync_value) if s.last_sync_value else None,
                "rows": s.rows_synced,
                "status": s.sync_status,
                "error": s.error_message,
            }
            for s in self.state.get_all_states()
        ]


def load_config(path: str) -> ReplicationConfig:
    """Load replication config from YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    databases = [
        DatabaseConfig(
            name=db["name"],
            tables=[
                TableConfig(
                    name=t["name"],
                    primary_key=t["primary_key"],
                    cdc_column=t.get("cdc_column"),
                )
                for t in db["tables"]
            ],
        )
        for db in raw["source"]["databases"]
    ]

    return ReplicationConfig(
        source_host=raw["source"]["host"],
        source_port=raw["source"]["port"],
        source_secret_name=raw["source"]["secret_name"],
        databases=databases,
        target_database=raw["target"]["database"],
        target_schema_pattern=raw["target"]["schema_pattern"],
        driver=raw["source"].get("driver", "psycopg2"),
        fetch_size=raw.get("extraction", {}).get("fetch_size", 50_000),
        batch_size=raw.get("extraction", {}).get("batch_size", 100_000),
        large_table_threshold=raw.get("extraction", {}).get("large_table_threshold", LARGE_TABLE_THRESHOLD),
        num_partitions=raw.get("extraction", {}).get("num_partitions", 4),
        source_timezone=raw["source"].get("timezone", "UTC"),
    )
