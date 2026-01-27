"""
Functional/Integration tests - hit real Postgres and Snowflake.

Run with: pytest tests/test_integration.py -v

Requires:
  - SNOWFLAKE_CONNECTION_NAME env var
  - PG_USER and PG_PASSWORD env vars
  - Access to the test Postgres instance

NOTE: Tests that use session.read.dbapi() will fail locally because
Snowpark serializes the connection factory and runs it in a subprocess.
These tests pass when run inside Snowflake stored procedures.
"""

import os
import pytest
from datetime import datetime

requires_snowflake = pytest.mark.skipif(
    not os.getenv("SNOWFLAKE_CONNECTION_NAME"),
    reason="Requires SNOWFLAKE_CONNECTION_NAME"
)

requires_postgres = pytest.mark.skipif(
    not os.getenv("PG_USER") or not os.getenv("PG_PASSWORD"),
    reason="Requires PG_USER and PG_PASSWORD"
)

dbapi_local_skip = pytest.mark.skip(
    reason="session.read.dbapi() requires Snowflake stored procedure environment"
)


@pytest.fixture(scope="module")
def snowpark_session():
    """Create real Snowpark session."""
    import snowflake.connector
    from snowflake.snowpark import Session

    conn = snowflake.connector.connect(
        connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME")
    )
    session = Session.builder.configs({"connection": conn}).create()
    yield session
    session.close()


@pytest.fixture(scope="module")
def test_config():
    """Load test config."""
    from dbapi_cdc.replicator import load_config
    config_path = os.path.join(
        os.path.dirname(__file__), 
        "../config/replication_config.yaml"
    )
    return load_config(config_path)


@requires_postgres
class TestPostgresConnection:
    """Test actual Postgres connectivity."""

    def test_connect_to_postgres(self, test_config):
        """Verify we can connect to Postgres."""
        import psycopg2

        conn = psycopg2.connect(
            host=test_config.source_host,
            port=test_config.source_port,
            dbname=test_config.databases[0].name,
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            sslmode="require",
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()

        assert result[0] == 1

    def test_query_users_table(self, test_config):
        """Verify users table exists and has data."""
        import psycopg2

        conn = psycopg2.connect(
            host=test_config.source_host,
            port=test_config.source_port,
            dbname=test_config.databases[0].name,
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            sslmode="require",
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM public.users")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()

        assert count > 0, "Users table should have data"


@dbapi_local_skip
@requires_postgres
@requires_snowflake
class TestExtractorIntegration:
    """Test Extractor against real Postgres."""

    def test_get_count(self, snowpark_session, test_config):
        """Get actual row count from source."""
        from dbapi_cdc.extractor import Extractor, ExtractionConfig

        extractor = Extractor(
            session=snowpark_session,
            host=test_config.source_host,
            port=test_config.source_port,
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            driver="psycopg2",
        )

        cfg = ExtractionConfig(
            host=test_config.source_host,
            port=test_config.source_port,
            database=test_config.databases[0].name,
            table="users",
            primary_key=["user_id"],
        )

        count = extractor.get_count(cfg)
        assert count > 0
        print(f"\nSource users count: {count}")

    def test_get_schema(self, snowpark_session, test_config):
        """Infer schema from source table."""
        from dbapi_cdc.extractor import Extractor, ExtractionConfig

        extractor = Extractor(
            session=snowpark_session,
            host=test_config.source_host,
            port=test_config.source_port,
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            driver="psycopg2",
        )

        cfg = ExtractionConfig(
            host=test_config.source_host,
            port=test_config.source_port,
            database=test_config.databases[0].name,
            table="users",
            primary_key=["user_id"],
        )

        df = extractor.extract(cfg)
        field_names = [f.name for f in df.schema.fields]

        assert "USER_ID" in field_names
        assert "UPDATED_AT" in field_names
        print(f"\nSchema fields: {field_names}")

    def test_extract_sample(self, snowpark_session, test_config):
        """Extract a small sample of data."""
        from dbapi_cdc.extractor import Extractor, ExtractionConfig

        extractor = Extractor(
            session=snowpark_session,
            host=test_config.source_host,
            port=test_config.source_port,
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            driver="psycopg2",
        )

        cfg = ExtractionConfig(
            host=test_config.source_host,
            port=test_config.source_port,
            database=test_config.databases[0].name,
            table="users",
            primary_key=["user_id"],
            fetch_size=100,
        )

        df = extractor.extract(cfg)
        count = df.count()

        assert count > 0
        print(f"\nExtracted {count} rows")

    def test_get_max_watermark(self, snowpark_session, test_config):
        """Get max watermark from source."""
        from dbapi_cdc.extractor import Extractor, ExtractionConfig

        extractor = Extractor(
            session=snowpark_session,
            host=test_config.source_host,
            port=test_config.source_port,
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
            driver="psycopg2",
        )

        cfg = ExtractionConfig(
            host=test_config.source_host,
            port=test_config.source_port,
            database=test_config.databases[0].name,
            table="users",
            primary_key=["user_id"],
            cdc_column="updated_at",
        )

        watermark = extractor.get_max_watermark(cfg)

        assert watermark is not None
        assert isinstance(watermark, datetime)
        print(f"\nMax watermark: {watermark}")


@requires_snowflake
class TestLoaderIntegration:
    """Test Loader against real Snowflake."""

    def test_table_exists(self, snowpark_session):
        """Check if replicated table exists."""
        from dbapi_cdc.loader import Loader, LoadConfig

        loader = Loader(snowpark_session)
        cfg = LoadConfig(
            target_database="DBAPI_REPLICA_DB",
            target_schema="CUSTOMER_A_DB_RAW",
            target_table="USERS",
            primary_key=["USER_ID"],
        )

        exists = loader.table_exists(cfg)
        print(f"\nTable exists: {exists}")

    def test_get_count(self, snowpark_session):
        """Get row count from target table."""
        from dbapi_cdc.loader import Loader, LoadConfig

        loader = Loader(snowpark_session)
        cfg = LoadConfig(
            target_database="DBAPI_REPLICA_DB",
            target_schema="CUSTOMER_A_DB_RAW",
            target_table="USERS",
            primary_key=["USER_ID"],
        )

        if loader.table_exists(cfg):
            count = loader.get_count(cfg)
            assert count > 0
            print(f"\nTarget users count: {count}")
        else:
            pytest.skip("Target table doesn't exist yet")


@requires_snowflake
class TestStateIntegration:
    """Test StateManager against real Snowflake."""

    def test_get_all_states(self, snowpark_session):
        """Get all replication states."""
        from dbapi_cdc.state import StateManager

        state_mgr = StateManager(snowpark_session, "DBAPI_REPLICA_DB")
        state_mgr.ensure_state_table()

        states = state_mgr.get_all_states()
        print(f"\nReplication states: {len(states)}")

        for s in states:
            print(f"  {s.source_db}.{s.table_name}: {s.sync_status} ({s.rows_synced} rows)")

    def test_get_high_watermark(self, snowpark_session):
        """Get watermark for a specific table."""
        from dbapi_cdc.state import StateManager

        state_mgr = StateManager(snowpark_session, "DBAPI_REPLICA_DB")
        watermark = state_mgr.get_high_watermark("customer_a_db", "users")

        if watermark:
            print(f"\nHigh watermark for customer_a_db.users: {watermark}")
        else:
            print("\nNo watermark found (table not yet synced)")


@dbapi_local_skip
@requires_postgres
@requires_snowflake
class TestEndToEnd:
    """End-to-end replication test."""

    def test_sync_single_table(self, snowpark_session, test_config):
        """Sync a single table end-to-end."""
        from dbapi_cdc.replicator import Replicator

        replicator = Replicator(snowpark_session, test_config)

        table_config = test_config.databases[0].tables[0]
        result = replicator.sync_table(
            test_config.databases[0].name,
            table_config,
            full_refresh=False,
        )

        assert result["status"] == "success"
        print(f"\nSync result: {result}")

    def test_replication_status(self, snowpark_session, test_config):
        """Check replication status."""
        from dbapi_cdc.replicator import Replicator

        replicator = Replicator(snowpark_session, test_config)
        status = replicator.status()

        print(f"\nReplication status:")
        for s in status:
            print(f"  {s['source_db']}.{s['table']}: {s['status']} ({s['rows']} rows)")

        assert len(status) > 0
