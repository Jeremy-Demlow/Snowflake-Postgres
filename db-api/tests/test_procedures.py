"""Tests for procedures module."""

import pytest

from dbapi_cdc.procedures import _parse_config


class TestParseConfig:
    def test_parse_minimal(self):
        yaml_str = """
source:
  driver: psycopg2
  host: "localhost"
  port: 5432
  secret_name: "SECRET"
  databases:
    - name: mydb
      tables:
        - name: users
          primary_key: [id]
target:
  database: REPLICA
  schema_pattern: "{source_db}_RAW"
"""
        cfg = _parse_config(yaml_str)

        assert cfg.source_host == "localhost"
        assert cfg.source_port == 5432
        assert cfg.driver == "psycopg2"
        assert cfg.target_database == "REPLICA"
        assert len(cfg.databases) == 1
        assert cfg.databases[0].tables[0].name == "users"

    def test_parse_with_extraction_settings(self):
        yaml_str = """
source:
  driver: pymssql
  host: "sqlserver.example.com"
  port: 1433
  secret_name: "SECRET"
  databases:
    - name: sales
      tables:
        - name: orders
          primary_key: [order_id]
          cdc_column: modified_at
target:
  database: DW
  schema_pattern: "{source_db}"
extraction:
  fetch_size: 10000
  batch_size: 25000
"""
        cfg = _parse_config(yaml_str)

        assert cfg.driver == "pymssql"
        assert cfg.fetch_size == 10000
        assert cfg.batch_size == 25000
        assert cfg.databases[0].tables[0].cdc_column == "modified_at"

    def test_parse_multiple_databases(self):
        yaml_str = """
source:
  host: "host"
  port: 5432
  secret_name: "SECRET"
  databases:
    - name: db1
      tables:
        - name: t1
          primary_key: [id]
    - name: db2
      tables:
        - name: t2
          primary_key: [id]
        - name: t3
          primary_key: [id]
target:
  database: TARGET
  schema_pattern: "{source_db}"
"""
        cfg = _parse_config(yaml_str)

        assert len(cfg.databases) == 2
        assert cfg.databases[0].name == "db1"
        assert cfg.databases[1].name == "db2"
        assert len(cfg.databases[1].tables) == 2
