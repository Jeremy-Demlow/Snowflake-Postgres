"""
Loader: Load DataFrames into Snowflake tables.

Uses native Snowpark merge for upserts - no staging tables needed.
"""

from dataclasses import dataclass
from typing import Optional

from snowflake.snowpark import DataFrame, Session
from snowflake.snowpark.exceptions import SnowparkSQLException
from snowflake.snowpark.functions import current_timestamp, when_matched, when_not_matched

__all__ = ["Loader", "LoadConfig"]


@dataclass
class LoadConfig:
    """Configuration for loading data into a target table."""
    target_database: str
    target_schema: str
    target_table: str
    primary_key: list[str]
    cdc_column: Optional[str] = None


class Loader:
    """Load DataFrames into Snowflake tables."""

    def __init__(self, session: Session):
        self.session = session

    def _full_name(self, config: LoadConfig) -> str:
        return f"{config.target_database}.{config.target_schema}.{config.target_table}"

    def ensure_schema(self, database: str, schema: str) -> None:
        """Create schema if it doesn't exist."""
        self.session.sql(f"CREATE SCHEMA IF NOT EXISTS {database}.{schema}").collect()

    def table_exists(self, config: LoadConfig) -> bool:
        """Check if target table exists."""
        try:
            self.session.sql(f"SELECT 1 FROM {self._full_name(config)} LIMIT 0").collect()
            return True
        except SnowparkSQLException:
            return False

    def create_table(self, config: LoadConfig, source_df: DataFrame) -> None:
        """Create target table from DataFrame schema."""
        self.ensure_schema(config.target_database, config.target_schema)
        full_name = self._full_name(config)

        source_df.limit(0).write.save_as_table(full_name, mode="errorifexists", table_type="")

        pk_cols = ", ".join(config.primary_key)
        self.session.sql(f"""
            ALTER TABLE {full_name}
            ADD CONSTRAINT pk_{config.target_table} PRIMARY KEY ({pk_cols})
        """).collect()

    def load_full(self, config: LoadConfig, source_df: DataFrame) -> int:
        """Full load - truncate and reload all data."""
        if not self.table_exists(config):
            self.create_table(config, source_df)

        source_df = source_df.with_column("_LOADED_AT", current_timestamp())
        source_df.write.save_as_table(self._full_name(config), mode="overwrite")
        return self.get_count(config)

    def load_merge(self, config: LoadConfig, source_df: DataFrame) -> int:
        """Incremental load using MERGE (upsert)."""
        if not self.table_exists(config):
            return self.load_full(config, source_df)

        source_df = source_df.with_column("_LOADED_AT", current_timestamp())
        row_count = source_df.count()
        if row_count == 0:
            return 0

        target = self.session.table(self._full_name(config))

        pk_cond = None
        for pk in config.primary_key:
            cond = target[pk] == source_df[pk]
            pk_cond = cond if pk_cond is None else pk_cond & cond

        pk_upper = {pk.upper() for pk in config.primary_key}
        update_cols = {c: source_df[c] for c in source_df.columns if c.upper() not in pk_upper}
        insert_cols = {c: source_df[c] for c in source_df.columns}

        target.merge(
            source_df,
            pk_cond,
            [when_matched().update(update_cols), when_not_matched().insert(insert_cols)],
        )
        return row_count

    def get_count(self, config: LoadConfig) -> int:
        """Get row count from target table."""
        result = self.session.sql(f"SELECT COUNT(*) as cnt FROM {self._full_name(config)}").collect()
        return int(result[0]["CNT"]) if result else 0

    def get_max_watermark(self, config: LoadConfig):
        """Get max CDC column value from target table."""
        if not config.cdc_column:
            return None
        result = self.session.sql(
            f"SELECT MAX({config.cdc_column}) as v FROM {self._full_name(config)}"
        ).collect()
        return result[0]["V"] if result and result[0]["V"] else None

    def truncate(self, config: LoadConfig) -> None:
        """Truncate target table."""
        self.session.sql(f"TRUNCATE TABLE IF EXISTS {self._full_name(config)}").collect()

    def drop(self, config: LoadConfig) -> None:
        """Drop target table."""
        self.session.sql(f"DROP TABLE IF EXISTS {self._full_name(config)}").collect()
