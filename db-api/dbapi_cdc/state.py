"""
State Management for CDC Replication

Tracks high watermarks per table to enable incremental syncs.
Stores state in Snowflake table: _REPLICATION_STATE
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from snowflake.snowpark import Session


@dataclass
class TableState:
    source_db: str
    table_name: str
    last_sync_value: Optional[datetime]
    last_sync_ts: Optional[datetime]
    rows_synced: int
    sync_status: str
    error_message: Optional[str]


class StateManager:
    def __init__(
        self,
        session: Session,
        database: str,
        schema: str = "PUBLIC",
        table: str = "_REPLICATION_STATE",
    ):
        self.session = session
        self.database = database
        self.schema = schema
        self.table = table
        self.full_table_name = f"{database}.{schema}.{table}"

    def ensure_state_table(self) -> None:
        self.session.sql(f"""
            CREATE TABLE IF NOT EXISTS {self.full_table_name} (
                source_db       VARCHAR(255) NOT NULL,
                table_name      VARCHAR(255) NOT NULL,
                last_sync_value TIMESTAMP_NTZ,
                last_sync_ts    TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
                rows_synced     NUMBER DEFAULT 0,
                sync_status     VARCHAR(50) DEFAULT 'pending',
                error_message   VARCHAR(4000),
                PRIMARY KEY (source_db, table_name)
            )
        """).collect()

    def get_state(self, source_db: str, table_name: str) -> Optional[TableState]:
        result = self.session.sql(f"""
            SELECT source_db, table_name, last_sync_value, last_sync_ts,
                   rows_synced, sync_status, error_message
            FROM {self.full_table_name}
            WHERE source_db = '{source_db}' AND table_name = '{table_name}'
        """).collect()

        if not result:
            return None

        row = result[0]
        return TableState(
            source_db=row["SOURCE_DB"],
            table_name=row["TABLE_NAME"],
            last_sync_value=row["LAST_SYNC_VALUE"],
            last_sync_ts=row["LAST_SYNC_TS"],
            rows_synced=row["ROWS_SYNCED"],
            sync_status=row["SYNC_STATUS"],
            error_message=row["ERROR_MESSAGE"],
        )

    def get_high_watermark(self, source_db: str, table_name: str) -> Optional[datetime]:
        state = self.get_state(source_db, table_name)
        return state.last_sync_value if state else None

    def update_state(
        self,
        source_db: str,
        table_name: str,
        last_sync_value: Optional[datetime] = None,
        rows_synced: int = 0,
        sync_status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        error_val = f"'{error_message[:4000].replace(chr(39), chr(39)+chr(39))}'" if error_message else "NULL"
        sync_val = f"'{last_sync_value.isoformat()}'" if last_sync_value else "NULL"

        self.session.sql(f"""
            MERGE INTO {self.full_table_name} AS target
            USING (
                SELECT
                    '{source_db}' AS source_db,
                    '{table_name}' AS table_name,
                    {sync_val}::TIMESTAMP_NTZ AS last_sync_value,
                    CURRENT_TIMESTAMP() AS last_sync_ts,
                    {rows_synced} AS rows_synced,
                    '{sync_status}' AS sync_status,
                    {error_val} AS error_message
            ) AS source
            ON target.source_db = source.source_db
               AND target.table_name = source.table_name
            WHEN MATCHED THEN UPDATE SET
                last_sync_value = source.last_sync_value,
                last_sync_ts = source.last_sync_ts,
                rows_synced = source.rows_synced,
                sync_status = source.sync_status,
                error_message = source.error_message
            WHEN NOT MATCHED THEN INSERT (
                source_db, table_name, last_sync_value, last_sync_ts,
                rows_synced, sync_status, error_message
            ) VALUES (
                source.source_db, source.table_name, source.last_sync_value,
                source.last_sync_ts, source.rows_synced, source.sync_status,
                source.error_message
            )
        """).collect()

    def mark_running(self, source_db: str, table_name: str) -> None:
        existing = self.get_state(source_db, table_name)
        if existing:
            self.session.sql(f"""
                UPDATE {self.full_table_name}
                SET sync_status = 'running', last_sync_ts = CURRENT_TIMESTAMP()
                WHERE source_db = '{source_db}' AND table_name = '{table_name}'
            """).collect()
        else:
            self.update_state(source_db, table_name, sync_status="running")

    def mark_completed(
        self,
        source_db: str,
        table_name: str,
        last_sync_value: datetime,
        rows_synced: int,
    ) -> None:
        self.update_state(
            source_db,
            table_name,
            last_sync_value=last_sync_value,
            rows_synced=rows_synced,
            sync_status="completed",
        )

    def mark_failed(self, source_db: str, table_name: str, error: str) -> None:
        self.update_state(
            source_db,
            table_name,
            sync_status="failed",
            error_message=error,
        )

    def get_all_states(self) -> list[TableState]:
        result = self.session.sql(f"""
            SELECT source_db, table_name, last_sync_value, last_sync_ts,
                   rows_synced, sync_status, error_message
            FROM {self.full_table_name}
            ORDER BY source_db, table_name
        """).collect()

        return [
            TableState(
                source_db=row["SOURCE_DB"],
                table_name=row["TABLE_NAME"],
                last_sync_value=row["LAST_SYNC_VALUE"],
                last_sync_ts=row["LAST_SYNC_TS"],
                rows_synced=row["ROWS_SYNCED"],
                sync_status=row["SYNC_STATUS"],
                error_message=row["ERROR_MESSAGE"],
            )
            for row in result
        ]

    def reset_state(self, source_db: str, table_name: str) -> None:
        self.session.sql(f"""
            DELETE FROM {self.full_table_name}
            WHERE source_db = '{source_db}' AND table_name = '{table_name}'
        """).collect()

    def reset_all(self) -> None:
        self.session.sql(f"TRUNCATE TABLE {self.full_table_name}").collect()
