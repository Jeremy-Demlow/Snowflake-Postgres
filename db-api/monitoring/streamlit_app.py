"""
CDC Pipeline Monitoring Dashboard - Command Tower
"""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSQLException

st.set_page_config(
    page_title="CDC Pipeline Monitor",
    page_icon=":material/monitoring:",
    layout="wide",
)

DATABASE = "DBAPI_REPLICA_DB"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "replication_config.yaml"


@st.cache_resource
def get_session():
    return Session.builder.config("connection_name", os.getenv("SNOWFLAKE_CONNECTION_NAME", "myconnection")).create()


def reset_connection():
    """Clear cached session and reconnect."""
    st.cache_resource.clear()
    st.cache_data.clear()


@st.cache_data(ttl=60)
def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run_query(sql: str) -> pd.DataFrame:
    try:
        session = get_session()
        return session.sql(sql).to_pandas()
    except SnowparkSQLException as e:
        if "390114" in str(e) or "Authentication token has expired" in str(e):
            st.error(":material/error: Session expired. Click 'Reconnect' to re-authenticate.")
            st.session_state["session_expired"] = True
            return pd.DataFrame()
        raise


def execute_sql(sql: str):
    try:
        session = get_session()
        session.sql(sql).collect()
    except SnowparkSQLException as e:
        if "390114" in str(e) or "Authentication token has expired" in str(e):
            st.error(":material/error: Session expired. Click 'Reconnect' to re-authenticate.")
            st.session_state["session_expired"] = True
            return
        raise


@st.cache_data(ttl=300)
def get_source_row_counts():
    return run_query("CALL DBAPI_REPLICA_DB.UTILS.GET_SOURCE_ROW_COUNTS()")


st.title(":material/monitoring: CDC Pipeline Monitor")

col1, col2, col3, _ = st.columns([2, 2, 2, 2])
with col1:
    if st.button(":material/sync: Run Sync", type="primary", help="Execute CDC replication from source to Snowflake", use_container_width=True):
        with st.spinner("Triggering sync task..."):
            execute_sql("EXECUTE TASK DBAPI_REPLICA_DB.UTILS.DBAPI_REPLICATION_DAG")
            st.toast("Sync task triggered!", icon=":material/check:")
            st.cache_data.clear()
with col2:
    if st.button(":material/refresh: Refresh Dashboard", help="Reload dashboard data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with col3:
    if st.button(":material/link: Reconnect", help="Re-establish Snowflake connection", use_container_width=True):
        reset_connection()
        st.session_state["session_expired"] = False
        st.toast("Reconnecting...", icon=":material/sync:")
        st.rerun()

tab0, tab1, tab2, tab3, tab4 = st.tabs([
    ":material/speed: Status",
    ":material/vital_signs: Health",
    ":material/compare_arrows: Source vs Target",
    ":material/history: Task History",
    ":material/database: Replication State"
])

with tab0:
    st.subheader("Sync Status Overview")
    st.caption("Quick view of database readiness and sync status")

    source_df = get_source_row_counts()
    
    target_df = run_query("""
        SELECT 
            REPLACE(LOWER(TABLE_SCHEMA), '_raw', '') as SOURCE_DB,
            LOWER(TABLE_NAME) as TABLE_NAME,
            ROW_COUNT as TARGET_ROWS
        FROM DBAPI_REPLICA_DB.INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_TYPE = 'BASE TABLE' 
          AND TABLE_SCHEMA LIKE '%_RAW'
    """)
    
    state_df = run_query("""
        SELECT SOURCE_DB, TABLE_NAME, SYNC_STATUS, LAST_SYNC_TS
        FROM DBAPI_REPLICA_DB.PUBLIC._REPLICATION_STATE
    """)
    
    if not source_df.empty and not target_df.empty:
        source_df["SOURCE_DB"] = source_df["SOURCE_DB"].str.lower()
        source_df["TABLE_NAME"] = source_df["TABLE_NAME"].str.lower()
        target_df["SOURCE_DB"] = target_df["SOURCE_DB"].str.lower()
        target_df["TABLE_NAME"] = target_df["TABLE_NAME"].str.lower()
        
        comparison = source_df.merge(target_df, on=["SOURCE_DB", "TABLE_NAME"], how="outer")
        comparison["IN_SYNC"] = comparison["SOURCE_ROWS"] == comparison["TARGET_ROWS"]
        
        in_sync = comparison["IN_SYNC"].sum()
        out_of_sync = len(comparison) - in_sync
        total_source = comparison["SOURCE_ROWS"].sum()
        total_target = comparison["TARGET_ROWS"].sum()
        drift = total_source - total_target
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("In Sync", f"{in_sync}/{len(comparison)}", delta="OK" if out_of_sync == 0 else None)
        c2.metric("Out of Sync", out_of_sync, delta=f"{out_of_sync} tables" if out_of_sync > 0 else None, delta_color="inverse")
        c3.metric("Source Rows", f"{total_source:,.0f}")
        c4.metric("Row Drift", f"{drift:+,.0f}", delta_color="inverse" if drift != 0 else "off")
        
        if out_of_sync == 0:
            st.success(":material/check_circle: All tables are in sync!")
        else:
            st.warning(f":material/warning: {out_of_sync} table(s) need syncing - click 'Run Sync Now' to update")
        
        st.divider()
        
        config = load_config()
        databases = config["source"]["databases"]
        
        for db_config in databases:
            db_name = db_config["name"].lower()
            db_comparison = comparison[comparison["SOURCE_DB"] == db_name]
            
            if not db_comparison.empty:
                db_in_sync = int(db_comparison["IN_SYNC"].sum())
                db_total = len(db_comparison)
                status_icon = ":material/check_circle:" if db_in_sync == db_total else ":material/warning:"
                is_expanded = bool(db_in_sync < db_total)
                
                with st.expander(f"{status_icon} **{db_name}** - {db_in_sync}/{db_total} tables in sync", expanded=is_expanded):
                    for _, row in db_comparison.iterrows():
                        table = row["TABLE_NAME"]
                        src = int(row["SOURCE_ROWS"]) if pd.notna(row["SOURCE_ROWS"]) else 0
                        tgt = int(row["TARGET_ROWS"]) if pd.notna(row["TARGET_ROWS"]) else 0
                        diff = tgt - src
                        
                        if diff == 0:
                            st.markdown(f":material/check_circle: **{table}** - {src:,} rows")
                        elif diff > 0:
                            st.markdown(f":material/arrow_upward: **{table}** - Source: {src:,} | Target: {tgt:,} (+{diff:,})")
                        else:
                            st.markdown(f":material/arrow_downward: **{table}** - Source: {src:,} | Target: {tgt:,} ({diff:,})")
    else:
        st.error(":material/error: Unable to retrieve source data")

with tab1:
    st.subheader("Pipeline Health")

    state_health = run_query("""
        SELECT SOURCE_DB, TABLE_NAME, SYNC_STATUS, ROWS_SYNCED,
               LAST_SYNC_TS, LAST_SYNC_VALUE, ERROR_MESSAGE
        FROM DBAPI_REPLICA_DB.PUBLIC._REPLICATION_STATE
        ORDER BY SOURCE_DB, TABLE_NAME
    """)

    tables_df = run_query("""
        SELECT TABLE_SCHEMA, TABLE_NAME, ROW_COUNT, BYTES, LAST_ALTERED
        FROM DBAPI_REPLICA_DB.INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_TYPE = 'BASE TABLE' 
          AND TABLE_SCHEMA LIKE '%_RAW'
        ORDER BY TABLE_SCHEMA, TABLE_NAME
    """)

    task_df = run_query("""
        SELECT NAME, STATE, SCHEDULED_TIME, COMPLETED_TIME, 
               TIMESTAMPDIFF('second', SCHEDULED_TIME, COMPLETED_TIME) as DURATION_SEC,
               ERROR_MESSAGE, QUERY_ID
        FROM TABLE(DBAPI_REPLICA_DB.INFORMATION_SCHEMA.TASK_HISTORY(
            TASK_NAME => 'DBAPI_REPLICATION_DAG',
            SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
        ))
        ORDER BY SCHEDULED_TIME DESC
        LIMIT 10
    """)

    failed = state_health[state_health["SYNC_STATUS"] == "failed"]
    succeeded = task_df[task_df["STATE"] == "SUCCEEDED"]
    total_rows = tables_df["ROW_COUNT"].sum() if not tables_df.empty else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tables Tracked", len(state_health))
    m2.metric("Total Rows", f"{total_rows:,.0f}")
    m3.metric("Failed Syncs", len(failed), delta=None if len(failed) == 0 else f"{len(failed)} errors", delta_color="inverse")
    m4.metric("Recent Runs", len(succeeded), help="Successful runs in last 7 days")

    if len(failed) > 0:
        st.error(f":material/error: {len(failed)} table(s) have sync failures")
        for _, row in failed.iterrows():
            st.code(f"{row['SOURCE_DB']}.{row['TABLE_NAME']}: {row['ERROR_MESSAGE']}")
    else:
        st.success(":material/check_circle: All syncs healthy")

    if not task_df.empty:
        last_run = task_df.iloc[0]
        last_time = pd.to_datetime(last_run["COMPLETED_TIME"])
        if pd.notna(last_time):
            st.info(f":material/schedule: Last sync completed: {last_time.strftime('%Y-%m-%d %H:%M:%S')} ({last_run['STATE']})")

with tab2:
    st.subheader("Source vs Target Comparison")
    st.caption("Live comparison of row counts between source database and Snowflake target")
    
    with st.spinner("Querying source database via stored procedure..."):
        source_df = get_source_row_counts()
    
    target_df = run_query("""
        SELECT 
            REPLACE(LOWER(TABLE_SCHEMA), '_raw', '') as SOURCE_DB,
            LOWER(TABLE_NAME) as TABLE_NAME,
            ROW_COUNT as TARGET_ROWS
        FROM DBAPI_REPLICA_DB.INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_TYPE = 'BASE TABLE' 
          AND TABLE_SCHEMA LIKE '%_RAW'
    """)
    
    if not source_df.empty and not target_df.empty:
        source_df["SOURCE_DB"] = source_df["SOURCE_DB"].str.lower()
        source_df["TABLE_NAME"] = source_df["TABLE_NAME"].str.lower()
        target_df["SOURCE_DB"] = target_df["SOURCE_DB"].str.lower()
        target_df["TABLE_NAME"] = target_df["TABLE_NAME"].str.lower()
        
        comparison = source_df.merge(
            target_df, 
            on=["SOURCE_DB", "TABLE_NAME"], 
            how="outer"
        )
        
        comparison["DIFF"] = comparison["TARGET_ROWS"].fillna(0) - comparison["SOURCE_ROWS"].fillna(0)
        comparison["MATCH"] = comparison["SOURCE_ROWS"] == comparison["TARGET_ROWS"]
        comparison["STATUS"] = comparison.apply(
            lambda r: ":material/check_circle:" if r["MATCH"] else ":material/warning:", axis=1
        )
        
        matched = comparison["MATCH"].sum()
        total = len(comparison)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Tables Matched", f"{matched}/{total}")
        c2.metric("Total Source Rows", f"{comparison['SOURCE_ROWS'].sum():,.0f}")
        c3.metric("Total Target Rows", f"{comparison['TARGET_ROWS'].sum():,.0f}")
        
        display_comp = comparison[["SOURCE_DB", "TABLE_NAME", "SOURCE_ROWS", "TARGET_ROWS", "DIFF", "STATUS"]].copy()
        display_comp = display_comp.rename(columns={
            "SOURCE_DB": "Database",
            "TABLE_NAME": "Table",
            "SOURCE_ROWS": "Source Rows",
            "TARGET_ROWS": "Target Rows",
            "DIFF": "Difference",
            "STATUS": ""
        })
        
        st.dataframe(
            display_comp,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Source Rows": st.column_config.NumberColumn(format="%d"),
                "Target Rows": st.column_config.NumberColumn(format="%d"),
                "Difference": st.column_config.NumberColumn(format="%d"),
            }
        )
        
        mismatched = comparison[~comparison["MATCH"]]
        if len(mismatched) > 0:
            st.warning(f":material/warning: {len(mismatched)} table(s) have row count differences")
        else:
            st.success(":material/check_circle: All tables in sync!")
    elif source_df.empty:
        st.error(":material/error: Could not retrieve source row counts")
        st.dataframe(
            target_df.rename(columns={
                "SOURCE_DB": "Database",
                "TABLE_NAME": "Table", 
                "TARGET_ROWS": "Target Rows"
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No data available")

with tab3:
    st.subheader("Task Execution History")

    task_history = run_query("""
        SELECT 
            NAME,
            STATE,
            SCHEDULED_TIME,
            COMPLETED_TIME,
            TIMESTAMPDIFF('second', SCHEDULED_TIME, COMPLETED_TIME) as DURATION_SEC,
            ERROR_MESSAGE,
            QUERY_ID
        FROM TABLE(DBAPI_REPLICA_DB.INFORMATION_SCHEMA.TASK_HISTORY(
            TASK_NAME => 'DBAPI_REPLICATION_DAG',
            SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
        ))
        ORDER BY SCHEDULED_TIME DESC
    """)

    if not task_history.empty:
        display_history = task_history.rename(columns={
            "NAME": "Task",
            "STATE": "Status",
            "SCHEDULED_TIME": "Scheduled",
            "COMPLETED_TIME": "Completed",
            "DURATION_SEC": "Duration (s)",
            "ERROR_MESSAGE": "Error",
            "QUERY_ID": "Query ID"
        })

        st.dataframe(
            display_history,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn(),
                "Scheduled": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm:ss"),
                "Completed": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm:ss"),
                "Duration (s)": st.column_config.NumberColumn(format="%d"),
                "Query ID": st.column_config.TextColumn(),
            }
        )

        st.divider()

        st.subheader("Run Statistics")
        succeeded = task_history[task_history["STATE"] == "SUCCEEDED"]
        failed = task_history[task_history["STATE"] == "FAILED"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Runs", len(task_history))
        c2.metric("Success Rate", f"{len(succeeded)/len(task_history)*100:.0f}%" if len(task_history) > 0 else "N/A")
        c3.metric("Avg Duration", f"{succeeded['DURATION_SEC'].mean():.1f}s" if len(succeeded) > 0 else "N/A")

        if len(failed) > 0:
            st.error(f"{len(failed)} failed runs:")
            st.dataframe(failed[["SCHEDULED_TIME", "ERROR_MESSAGE"]], hide_index=True)
    else:
        st.info("No task history found")

with tab4:
    st.subheader("Replication State")

    state_with_rows = run_query("""
        SELECT 
            r.SOURCE_DB,
            r.TABLE_NAME,
            r.SYNC_STATUS,
            t.ROW_COUNT as TARGET_ROWS,
            r.LAST_SYNC_TS,
            r.LAST_SYNC_VALUE,
            r.ERROR_MESSAGE
        FROM DBAPI_REPLICA_DB.PUBLIC._REPLICATION_STATE r
        LEFT JOIN DBAPI_REPLICA_DB.INFORMATION_SCHEMA.TABLES t
            ON UPPER(r.SOURCE_DB) || '_RAW' = t.TABLE_SCHEMA
            AND UPPER(r.TABLE_NAME) = t.TABLE_NAME
        WHERE t.TABLE_TYPE = 'BASE TABLE' OR t.TABLE_TYPE IS NULL
        ORDER BY r.SOURCE_DB, r.TABLE_NAME
    """)

    display_state = state_with_rows.rename(columns={
        "SOURCE_DB": "Source DB",
        "TABLE_NAME": "Table",
        "SYNC_STATUS": "Status",
        "TARGET_ROWS": "Target Rows",
        "LAST_SYNC_TS": "Last Sync Time",
        "LAST_SYNC_VALUE": "Last Sync Value",
        "ERROR_MESSAGE": "Error"
    })

    st.dataframe(
        display_state,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(),
            "Target Rows": st.column_config.NumberColumn(format="%d"),
            "Last Sync Time": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm:ss"),
            "Last Sync Value": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm:ss"),
        }
    )

    st.divider()

    st.subheader("Status Breakdown")
    status_counts = state_with_rows["SYNC_STATUS"].value_counts()
    for status, count in status_counts.items():
        if status == "completed":
            st.success(f":material/check_circle: {count} tables completed")
        elif status == "failed":
            st.error(f":material/error: {count} tables failed")
        elif status == "pending":
            st.warning(f":material/pending: {count} tables pending")
        else:
            st.info(f":material/info: {count} tables - {status}")

st.divider()
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
