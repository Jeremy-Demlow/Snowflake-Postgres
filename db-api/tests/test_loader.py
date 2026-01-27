"""Tests for loader module."""

from unittest.mock import MagicMock, call

import pytest
from snowflake.snowpark.exceptions import SnowparkSQLException

from dbapi_cdc.loader import LoadConfig, Loader


class TestLoadConfig:
    def test_required_fields(self):
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
        )
        assert cfg.target_database == "DB"
        assert cfg.cdc_column is None

    def test_with_cdc_column(self):
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
            cdc_column="updated_at",
        )
        assert cfg.cdc_column == "updated_at"


class TestLoader:
    def test_full_name(self, mock_session):
        loader = Loader(mock_session)
        cfg = LoadConfig(
            target_database="MY_DB",
            target_schema="MY_SCHEMA",
            target_table="MY_TABLE",
            primary_key=["id"],
        )
        assert loader._full_name(cfg) == "MY_DB.MY_SCHEMA.MY_TABLE"

    def test_ensure_schema(self, mock_session):
        loader = Loader(mock_session)
        loader.ensure_schema("DB", "SCHEMA")

        mock_session.sql.assert_called_with("CREATE SCHEMA IF NOT EXISTS DB.SCHEMA")
        mock_session.sql.return_value.collect.assert_called_once()

    def test_table_exists_true(self, mock_session):
        loader = Loader(mock_session)
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
        )

        assert loader.table_exists(cfg) is True
        mock_session.sql.assert_called_with("SELECT 1 FROM DB.SCHEMA.TABLE LIMIT 0")

    def test_table_exists_false(self, mock_session):
        mock_session.sql.return_value.collect.side_effect = SnowparkSQLException("not found")

        loader = Loader(mock_session)
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
        )

        assert loader.table_exists(cfg) is False

    def test_get_count(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [{"CNT": 100}]

        loader = Loader(mock_session)
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
        )

        assert loader.get_count(cfg) == 100

    def test_get_max_watermark_no_cdc(self, mock_session):
        loader = Loader(mock_session)
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
        )

        assert loader.get_max_watermark(cfg) is None

    def test_truncate(self, mock_session):
        loader = Loader(mock_session)
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
        )

        loader.truncate(cfg)
        mock_session.sql.assert_called_with("TRUNCATE TABLE IF EXISTS DB.SCHEMA.TABLE")

    def test_drop(self, mock_session):
        loader = Loader(mock_session)
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
        )

        loader.drop(cfg)
        mock_session.sql.assert_called_with("DROP TABLE IF EXISTS DB.SCHEMA.TABLE")

    def test_load_merge_empty_df(self, mock_session):
        mock_df = MagicMock()
        mock_df.count.return_value = 0
        mock_df.with_column.return_value = mock_df

        loader = Loader(mock_session)
        cfg = LoadConfig(
            target_database="DB",
            target_schema="SCHEMA",
            target_table="TABLE",
            primary_key=["id"],
        )

        result = loader.load_merge(cfg, mock_df)
        assert result == 0
