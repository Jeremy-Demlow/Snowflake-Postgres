"""Pytest fixtures for dbapi-cdc tests."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_session():
    """Mock Snowpark session with DB-API reader."""
    session = MagicMock()
    session.sql.return_value.collect.return_value = []
    session.table.return_value = MagicMock()
    session.read.dbapi.return_value = MagicMock()
    return session


@pytest.fixture
def sample_config_yaml():
    """Sample YAML config for testing."""
    return """
source:
  driver: psycopg2
  host: "test.postgres.example.com"
  port: 5432
  secret_name: "TEST_DB.PUBLIC.PG_SECRET"
  databases:
    - name: test_db
      tables:
        - name: users
          primary_key: [user_id]
          cdc_column: updated_at
        - name: orders
          primary_key: [id]
          cdc_column: updated_at
target:
  database: TEST_REPLICA_DB
  schema_pattern: "{source_db}_RAW"
"""


@pytest.fixture
def mock_pg_cursor():
    """Mock psycopg2 cursor with schema info."""
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        ("user_id", "integer"),
        ("name", "varchar"),
        ("updated_at", "timestamp"),
    ]
    cursor.fetchone.return_value = (100,)
    cursor.fetchmany.return_value = []
    cursor.arraysize = 10000
    return cursor


@pytest.fixture
def mock_pg_connection(mock_pg_cursor):
    """Mock psycopg2 connection."""
    conn = MagicMock()
    conn.cursor.return_value = mock_pg_cursor
    return conn
