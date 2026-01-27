"""Tests for extractor module (Snowpark DB-API)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from dbapi_cdc.extractor import ExtractionConfig, Extractor


class TestExtractionConfig:
    def test_defaults(self):
        cfg = ExtractionConfig(
            host="localhost",
            port=5432,
            database="testdb",
            table="users",
            primary_key=["id"],
        )
        assert cfg.driver == "psycopg2"
        assert cfg.fetch_size == 50_000
        assert cfg.num_partitions == 4
        assert cfg.cdc_column is None

    def test_with_cdc_column(self):
        cfg = ExtractionConfig(
            host="localhost",
            port=5432,
            database="testdb",
            table="users",
            primary_key=["id"],
            cdc_column="updated_at",
        )
        assert cfg.cdc_column == "updated_at"


class TestExtractor:
    def test_create_connection_factory_postgres(self, mock_session):
        extractor = Extractor(
            session=mock_session,
            host="localhost",
            port=5432,
            user="testuser",
            password="testpass",
            driver="psycopg2",
        )
        factory = extractor._create_connection_factory("testdb")
        assert callable(factory)

    def test_create_connection_factory_unsupported(self, mock_session):
        extractor = Extractor(
            mock_session, "host", 5432, "user", "pass", driver="unknown"
        )
        with pytest.raises(ValueError, match="Unsupported driver"):
            extractor._create_connection_factory("testdb")

    def test_extract_calls_dbapi(self, mock_session):
        mock_df = MagicMock()
        mock_session.read.dbapi.return_value = mock_df
        
        extractor = Extractor(
            mock_session, "host", 5432, "user", "pass", driver="psycopg2"
        )
        cfg = ExtractionConfig(
            host="host", port=5432, database="db", table="users", primary_key=["id"]
        )
        
        result = extractor.extract(cfg)
        
        assert result == mock_df
        mock_session.read.dbapi.assert_called_once()

    def test_extract_with_watermark(self, mock_session):
        mock_df = MagicMock()
        mock_session.read.dbapi.return_value = mock_df
        
        extractor = Extractor(
            mock_session, "host", 5432, "user", "pass", driver="psycopg2"
        )
        cfg = ExtractionConfig(
            host="host", port=5432, database="db", table="users", 
            primary_key=["id"], cdc_column="updated_at"
        )
        watermark = datetime(2024, 1, 15, 10, 30, 0)
        
        result = extractor.extract(cfg, watermark)
        
        assert result == mock_df
        call_kwargs = mock_session.read.dbapi.call_args
        assert "query" in call_kwargs.kwargs

    def test_get_count(self, mock_session):
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value=42)
        mock_df = MagicMock()
        mock_df.collect.return_value = [mock_row]
        mock_session.read.dbapi.return_value = mock_df
        
        extractor = Extractor(
            mock_session, "host", 5432, "user", "pass", driver="psycopg2"
        )
        cfg = ExtractionConfig(
            host="host", port=5432, database="db", table="users", primary_key=["id"]
        )
        
        count = extractor.get_count(cfg)
        assert count == 42

    def test_get_max_watermark_no_cdc_column(self, mock_session):
        extractor = Extractor(
            mock_session, "host", 5432, "user", "pass", driver="psycopg2"
        )
        cfg = ExtractionConfig(
            host="host", port=5432, database="db", table="users", primary_key=["id"]
        )
        
        result = extractor.get_max_watermark(cfg)
        assert result is None

    def test_get_max_watermark_with_cdc(self, mock_session):
        ts = datetime(2024, 1, 15, 10, 30, 0)
        mock_row = MagicMock()
        mock_row.__getitem__ = MagicMock(return_value=ts)
        mock_df = MagicMock()
        mock_df.collect.return_value = [mock_row]
        mock_session.read.dbapi.return_value = mock_df
        
        extractor = Extractor(
            mock_session, "host", 5432, "user", "pass", driver="psycopg2"
        )
        cfg = ExtractionConfig(
            host="host", port=5432, database="db", table="users",
            primary_key=["id"], cdc_column="updated_at"
        )
        
        result = extractor.get_max_watermark(cfg)
        assert result == ts
