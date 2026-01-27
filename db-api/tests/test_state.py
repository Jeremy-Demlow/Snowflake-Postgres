"""Tests for state module."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from dbapi_cdc.state import StateManager, TableState


class TestTableState:
    def test_create(self):
        state = TableState(
            source_db="mydb",
            table_name="users",
            last_sync_value=datetime(2024, 1, 15),
            last_sync_ts=datetime(2024, 1, 15, 10, 0),
            rows_synced=1000,
            sync_status="completed",
            error_message=None,
        )
        assert state.source_db == "mydb"
        assert state.rows_synced == 1000


class TestStateManager:
    def test_init(self, mock_session):
        mgr = StateManager(mock_session, "MY_DB")
        assert mgr.full_table_name == "MY_DB.PUBLIC._REPLICATION_STATE"

    def test_init_custom_schema(self, mock_session):
        mgr = StateManager(mock_session, "MY_DB", schema="MONITORING")
        assert mgr.full_table_name == "MY_DB.MONITORING._REPLICATION_STATE"

    def test_ensure_state_table(self, mock_session):
        mgr = StateManager(mock_session, "MY_DB")
        mgr.ensure_state_table()

        call_args = mock_session.sql.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS" in call_args
        assert "_REPLICATION_STATE" in call_args

    def test_get_state_not_found(self, mock_session):
        mock_session.sql.return_value.collect.return_value = []

        mgr = StateManager(mock_session, "MY_DB")
        result = mgr.get_state("db", "table")

        assert result is None

    def test_get_state_found(self, mock_session):
        mock_session.sql.return_value.collect.return_value = [
            {
                "SOURCE_DB": "mydb",
                "TABLE_NAME": "users",
                "LAST_SYNC_VALUE": datetime(2024, 1, 15),
                "LAST_SYNC_TS": datetime(2024, 1, 15, 10, 0),
                "ROWS_SYNCED": 500,
                "SYNC_STATUS": "completed",
                "ERROR_MESSAGE": None,
            }
        ]

        mgr = StateManager(mock_session, "MY_DB")
        result = mgr.get_state("mydb", "users")

        assert result is not None
        assert result.source_db == "mydb"
        assert result.rows_synced == 500

    def test_get_high_watermark(self, mock_session):
        ts = datetime(2024, 1, 15, 12, 0)
        mock_session.sql.return_value.collect.return_value = [
            {
                "SOURCE_DB": "mydb",
                "TABLE_NAME": "users",
                "LAST_SYNC_VALUE": ts,
                "LAST_SYNC_TS": ts,
                "ROWS_SYNCED": 100,
                "SYNC_STATUS": "completed",
                "ERROR_MESSAGE": None,
            }
        ]

        mgr = StateManager(mock_session, "MY_DB")
        result = mgr.get_high_watermark("mydb", "users")

        assert result == ts

    def test_mark_running_new(self, mock_session):
        mock_session.sql.return_value.collect.return_value = []

        mgr = StateManager(mock_session, "MY_DB")
        mgr.mark_running("db", "table")

        calls = mock_session.sql.call_args_list
        assert len(calls) >= 2

    def test_mark_completed(self, mock_session):
        mgr = StateManager(mock_session, "MY_DB")
        mgr.mark_completed("db", "table", datetime(2024, 1, 15), 1000)

        call_args = mock_session.sql.call_args[0][0]
        assert "MERGE INTO" in call_args
        assert "completed" in call_args

    def test_mark_failed(self, mock_session):
        mgr = StateManager(mock_session, "MY_DB")
        mgr.mark_failed("db", "table", "Connection timeout")

        call_args = mock_session.sql.call_args[0][0]
        assert "failed" in call_args
        assert "Connection timeout" in call_args

    def test_reset_state(self, mock_session):
        mgr = StateManager(mock_session, "MY_DB")
        mgr.reset_state("db", "table")

        mock_session.sql.assert_called()
        call_args = mock_session.sql.call_args[0][0]
        assert "DELETE FROM" in call_args

    def test_reset_all(self, mock_session):
        mgr = StateManager(mock_session, "MY_DB")
        mgr.reset_all()

        mock_session.sql.assert_called_with("TRUNCATE TABLE MY_DB.PUBLIC._REPLICATION_STATE")
