"""Tests for replicator module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from dbapi_cdc.replicator import (
    DatabaseConfig,
    ReplicationConfig,
    TableConfig,
    load_config,
)


class TestTableConfig:
    def test_minimal(self):
        cfg = TableConfig(name="users", primary_key=["id"])
        assert cfg.name == "users"
        assert cfg.primary_key == ["id"]
        assert cfg.cdc_column is None

    def test_with_cdc(self):
        cfg = TableConfig(name="users", primary_key=["id"], cdc_column="updated_at")
        assert cfg.cdc_column == "updated_at"


class TestDatabaseConfig:
    def test_with_tables(self):
        tables = [
            TableConfig(name="users", primary_key=["id"]),
            TableConfig(name="orders", primary_key=["order_id"]),
        ]
        cfg = DatabaseConfig(name="mydb", tables=tables)
        assert cfg.name == "mydb"
        assert len(cfg.tables) == 2


class TestReplicationConfig:
    def test_defaults(self):
        cfg = ReplicationConfig(
            source_host="localhost",
            source_port=5432,
            source_secret_name="SECRET",
            databases=[],
            target_database="TARGET",
            target_schema_pattern="{source_db}_RAW",
        )
        assert cfg.driver == "psycopg2"
        assert cfg.fetch_size == 50_000
        assert cfg.batch_size == 100_000


class TestLoadConfig:
    def test_load_from_yaml(self):
        yaml_content = """
source:
  driver: psycopg2
  host: "test.host.com"
  port: 5432
  secret_name: "DB.SCHEMA.SECRET"
  databases:
    - name: db1
      tables:
        - name: users
          primary_key: [user_id]
          cdc_column: updated_at
        - name: orders
          primary_key: [id]
    - name: db2
      tables:
        - name: products
          primary_key: [product_id]
target:
  database: REPLICA_DB
  schema_pattern: "{source_db}_RAW"
extraction:
  fetch_size: 25000
  batch_size: 50000
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            cfg = load_config(f.name)

            assert cfg.source_host == "test.host.com"
            assert cfg.source_port == 5432
            assert cfg.driver == "psycopg2"
            assert cfg.target_database == "REPLICA_DB"
            assert cfg.target_schema_pattern == "{source_db}_RAW"
            assert cfg.fetch_size == 25000
            assert cfg.batch_size == 50000

            assert len(cfg.databases) == 2
            assert cfg.databases[0].name == "db1"
            assert len(cfg.databases[0].tables) == 2
            assert cfg.databases[0].tables[0].name == "users"
            assert cfg.databases[0].tables[0].cdc_column == "updated_at"
            assert cfg.databases[0].tables[1].cdc_column is None

            Path(f.name).unlink()

    def test_load_minimal_yaml(self):
        yaml_content = """
source:
  host: "localhost"
  port: 5432
  secret_name: "SECRET"
  databases:
    - name: mydb
      tables:
        - name: mytable
          primary_key: [id]
target:
  database: TARGET
  schema_pattern: "{source_db}"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            cfg = load_config(f.name)

            assert cfg.driver == "psycopg2"
            assert cfg.fetch_size == 50_000
            assert cfg.batch_size == 100_000

            Path(f.name).unlink()
