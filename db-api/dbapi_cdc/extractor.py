"""
Extractor: Pull data from external databases using Snowpark DB-API.

Uses session.read.dbapi() for efficient, parallelized data extraction.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from snowflake.snowpark import DataFrame, Session

__all__ = ["Extractor", "ExtractionConfig"]


@dataclass
class ExtractionConfig:
    """Configuration for extracting data from a source table."""
    host: str
    port: int
    database: str
    table: str
    primary_key: list[str]
    driver: str = "psycopg2"
    cdc_column: Optional[str] = None
    fetch_size: int = 50_000
    num_partitions: int = 4


class Extractor:
    """Extract data from external databases using Snowpark DB-API."""

    def __init__(
        self,
        session: Session,
        host: str,
        port: int,
        user: str,
        password: str,
        driver: str = "psycopg2",
    ):
        self.session = session
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.driver = driver

    def _create_connection_factory(self, database: str):
        """Return a factory function that creates DB-API connections."""
        host = self.host
        port = self.port
        user = self.user
        password = self.password
        driver = self.driver

        def create_pg_connection():
            import psycopg2
            return psycopg2.connect(
                host=host,
                port=port,
                dbname=database,
                user=user,
                password=password,
                sslmode="require",
                application_name="snowflake-snowpark-dbapi-cdc"
            )

        def create_mssql_connection():
            import pymssql
            return pymssql.connect(
                server=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )

        def create_mysql_connection():
            import pymysql
            return pymysql.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )

        if driver == "psycopg2":
            return create_pg_connection
        elif driver in ("pymssql", "mssql"):
            return create_mssql_connection
        elif driver in ("pymysql", "mysql"):
            return create_mysql_connection
        else:
            raise ValueError(f"Unsupported driver: {driver}")

    def extract(
        self, config: ExtractionConfig, watermark: Optional[datetime] = None
    ) -> DataFrame:
        """
        Extract data from source table using Snowpark DB-API.

        If watermark is provided, extracts rows where cdc_column > watermark.
        Otherwise extracts all rows.
        """
        conn_factory = self._create_connection_factory(config.database)
        table = f"public.{config.table}" if self.driver == "psycopg2" else config.table

        if watermark and config.cdc_column:
            ts = watermark.strftime("%Y-%m-%d %H:%M:%S.%f")
            query = f"SELECT * FROM {table} WHERE {config.cdc_column} > '{ts}'::timestamp"

            return self.session.read.dbapi(
                conn_factory,
                query=query,
                fetch_size=config.fetch_size,
            )
        else:
            return self.session.read.dbapi(
                conn_factory,
                table=table,
                fetch_size=config.fetch_size,
            )

    def extract_partitioned(
        self,
        config: ExtractionConfig,
        watermark: Optional[datetime] = None,
        partition_column: Optional[str] = None,
        lower_bound: int = 0,
        upper_bound: int = 1000000,
    ) -> DataFrame:
        """
        Extract data with parallelism using partition column.

        Use this for large tables to parallelize extraction.
        """
        conn_factory = self._create_connection_factory(config.database)
        table = f"public.{config.table}" if self.driver == "psycopg2" else config.table

        if watermark and config.cdc_column:
            ts = watermark.strftime("%Y-%m-%d %H:%M:%S.%f")
            query = f"SELECT * FROM {table} WHERE {config.cdc_column} > '{ts}'::timestamp"

            return self.session.read.dbapi(
                conn_factory,
                query=query,
                fetch_size=config.fetch_size,
                num_partitions=config.num_partitions,
                column=partition_column or config.primary_key[0],
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )
        else:
            return self.session.read.dbapi(
                conn_factory,
                table=table,
                fetch_size=config.fetch_size,
                num_partitions=config.num_partitions,
                column=partition_column or config.primary_key[0],
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )

    def get_max_watermark(self, config: ExtractionConfig) -> Optional[datetime]:
        """Get maximum value of CDC column."""
        if not config.cdc_column:
            return None

        conn_factory = self._create_connection_factory(config.database)
        table = f"public.{config.table}" if self.driver == "psycopg2" else config.table

        df = self.session.read.dbapi(
            conn_factory,
            query=f"SELECT MAX({config.cdc_column}) as max_val FROM {table}",
        )
        result = df.collect()
        return result[0]["MAX_VAL"] if result and result[0]["MAX_VAL"] else None

    def get_count(self, config: ExtractionConfig) -> int:
        """Get row count from source table."""
        conn_factory = self._create_connection_factory(config.database)
        table = f"public.{config.table}" if self.driver == "psycopg2" else config.table

        df = self.session.read.dbapi(
            conn_factory,
            query=f"SELECT COUNT(*) as cnt FROM {table}",
        )
        result = df.collect()
        return int(result[0]["CNT"]) if result else 0
