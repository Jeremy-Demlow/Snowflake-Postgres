"""
Snowflake stored procedure entry points.

These handlers are deployed as Snowflake stored procedures via `snow snowpark deploy`.
They read configuration from DATABASE_REGISTRY and TABLE_REGISTRY tables.

Supports three sync modes:
- 'full': Full table reload (overwrite)
- 'cdc': Change Data Capture using watermark column (incremental MERGE)
- 'wal': WAL-based CDC using PostgreSQL logical replication (captures INSERTs, UPDATEs, DELETEs)

IMPORTANT: This module must NOT import any module at the top level that imports
snowflake.snowpark or snowflake.connector - those imports fail in the Snowpark
procedure runtime when loading from a zip file.
"""

from __future__ import annotations

import hashlib
import time


def _get_credentials():
    """Get database credentials from Snowflake secret."""
    import _snowflake
    creds = _snowflake.get_username_password("creds")
    return creds.username, creds.password


def _get_pg_schema(cur, schema: str, table: str) -> list[tuple[str, str]]:
    """Get column names and types from PostgreSQL information_schema."""
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_schema = %s AND table_name = %s 
        ORDER BY ordinal_position
    """, (schema, table))
    return cur.fetchall()


def _compute_schema_fingerprint(columns: list[tuple[str, str]]) -> str:
    """Compute a hash fingerprint of the schema for change detection."""
    schema_str = "|".join(f"{name}:{dtype}" for name, dtype in columns)
    return hashlib.md5(schema_str.encode()).hexdigest()[:16]


def _get_sf_columns(session, full_target: str) -> set[str]:
    """Get existing column names from Snowflake table (uppercase)."""
    try:
        result = session.sql(f"DESCRIBE TABLE {full_target}").collect()
        return {row['name'].upper() for row in result}
    except:
        return set()


def _table_exists(session, full_target: str) -> bool:
    """Check if target table exists."""
    try:
        session.sql(f"SELECT 1 FROM {full_target} LIMIT 0").collect()
        return True
    except:
        return False


def _handle_schema_evolution(session, cur, source_schema: str, source_table: str, 
                             full_target: str, table_id: str) -> tuple[bool, str]:
    """
    Detect schema changes between PostgreSQL source and Snowflake target.
    
    IMPORTANT: This function does NOT update TABLE_REGISTRY directly to avoid
    lock contention when multiple tasks run in parallel. Schema fingerprints
    are returned but not persisted here.
    
    Returns: (schema_changed, message)
    - If new columns detected: returns True (will trigger full resync)
    - If columns removed: returns False (Snowflake keeps extra columns)
    """
    pg_columns = _get_pg_schema(cur, source_schema, source_table)
    new_fingerprint = _compute_schema_fingerprint(pg_columns)
    
    registry = session.sql(f"""
        SELECT SCHEMA_FINGERPRINT, SCHEMA_VERSION 
        FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY 
        WHERE TABLE_ID = '{table_id}'
    """).collect()
    
    old_fingerprint = registry[0]['SCHEMA_FINGERPRINT'] if registry and registry[0]['SCHEMA_FINGERPRINT'] else None
    old_version = registry[0]['SCHEMA_VERSION'] if registry and registry[0]['SCHEMA_VERSION'] else 0
    
    if old_fingerprint is None:
        return False, "Schema fingerprint initialized"
    
    if old_fingerprint == new_fingerprint:
        return False, "Schema unchanged"
    
    pg_col_names = {col[0].upper() for col in pg_columns}
    sf_columns = _get_sf_columns(session, full_target)
    
    new_columns = pg_col_names - sf_columns if sf_columns else set()
    removed_columns = sf_columns - pg_col_names if sf_columns else set()
    
    new_version = old_version + 1
    changes = []
    if new_columns:
        changes.append(f"+[{','.join(sorted(new_columns))}]")
    if removed_columns:
        changes.append(f"-[{','.join(sorted(removed_columns))}]")
    change_desc = " ".join(changes) if changes else "column type changes"
    
    return bool(new_columns), f"Schema evolved v{old_version}->v{new_version}: {change_desc}"


def _parse_pk_columns(pk_column: str) -> list[str]:
    """Parse primary key column(s) - supports composite keys via comma separation."""
    if not pk_column:
        return []
    return [col.strip() for col in pk_column.split(',')]


def _do_full_load(session, connection_factory, source_schema: str, source_table: str,
                  full_target: str, pk_column: str, batch_size: int) -> tuple[int, int, str]:
    """
    Full table load - SELECT * and overwrite.
    Supports composite primary keys for ORDER BY.
    
    Returns: (row_count, batches_used, mode_desc)
    """
    import psycopg2
    
    conn = connection_factory()
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM "{source_schema}"."{source_table}"')
    total_rows = cur.fetchone()[0]
    cur.close()
    conn.close()
    
    pk_cols = _parse_pk_columns(pk_column)
    
    if not pk_cols or total_rows <= batch_size:
        query = f'SELECT * FROM "{source_schema}"."{source_table}"'
        df = session.read.dbapi(connection_factory, query=query)
        df.write.mode("overwrite").save_as_table(full_target)
        batches_used = 1
    else:
        order_by = ', '.join(pk_cols)
        offset = 0
        batches_used = 0
        
        while offset < total_rows:
            query = f"""
                SELECT * FROM "{source_schema}"."{source_table}" 
                ORDER BY {order_by} 
                LIMIT {batch_size} OFFSET {offset}
            """
            df = session.read.dbapi(connection_factory, query=query)
            
            if offset == 0:
                df.write.mode("overwrite").save_as_table(full_target)
            else:
                df.write.mode("append").save_as_table(full_target)
            
            offset += batch_size
            batches_used += 1
    
    row_count = session.sql(f"SELECT COUNT(*) as cnt FROM {full_target}").collect()[0]['CNT']
    return row_count, batches_used, "FULL"


def _do_cdc_load(session, connection_factory, source_schema: str, source_table: str,
                 full_target: str, pk_column: str, cdc_column: str, 
                 last_watermark, batch_size: int) -> tuple[int, int, str, str]:
    """
    CDC incremental load - SELECT WHERE cdc_column > watermark, then MERGE.
    
    Returns: (row_count, batches_used, mode_desc, new_watermark)
    """
    from snowflake.snowpark.functions import col, when_matched, when_not_matched
    
    if last_watermark:
        watermark_filter = f'WHERE "{cdc_column}" > \'{last_watermark}\''
    else:
        watermark_filter = ""
    
    query = f'SELECT * FROM "{source_schema}"."{source_table}" {watermark_filter}'
    df = session.read.dbapi(connection_factory, query=query)
    
    source_count = df.count()
    
    if source_count == 0:
        return 0, 0, "CDC (no changes)", str(last_watermark) if last_watermark else None
    
    if not _table_exists(session, full_target):
        df.write.mode("overwrite").save_as_table(full_target)
        new_wm = session.sql(f'SELECT MAX("{cdc_column.upper()}") as wm FROM {full_target}').collect()[0]['WM']
        return source_count, 1, "CDC (initial)", str(new_wm) if new_wm else None
    
    target_table = session.table(full_target)
    pk_cols = _parse_pk_columns(pk_column)
    pk_cols_upper = [c.upper() for c in pk_cols]
    
    merge_condition = None
    for pk_col in pk_cols_upper:
        cond = target_table[pk_col] == df[pk_col]
        merge_condition = cond if merge_condition is None else (merge_condition & cond)
    
    source_cols = [c for c in df.columns]
    update_assignments = {c: df[c] for c in source_cols if c.upper() not in pk_cols_upper}
    insert_assignments = {c: df[c] for c in source_cols}
    
    target_table.merge(
        df,
        merge_condition,
        [
            when_matched().update(update_assignments),
            when_not_matched().insert(insert_assignments)
        ]
    )
    
    new_wm = session.sql(f'SELECT MAX("{cdc_column.upper()}") as wm FROM {full_target}').collect()[0]['WM']
    
    return source_count, 1, "CDC (merge)", str(new_wm) if new_wm else None


def _get_wal_changes(cur, slot_name: str, table_name: str, pk_column: str, limit: int = 10000, max_retries: int = 3) -> list[dict]:
    """
    Peek at WAL changes from a replication slot for a specific table.
    Uses test_decoding plugin output format.
    
    Includes retry logic for WAL slot contention (when another process holds the slot).
    
    Returns list of changes: {'action': 'I'|'U'|'D', 'pk': value}
    """
    import re
    import random
    
    for attempt in range(max_retries):
        try:
            cur.connection.rollback()  # Clear any aborted transaction state before each attempt
            cur.execute(f"""
                SELECT data FROM pg_logical_slot_peek_changes(
                    '{slot_name}', NULL, {limit}
                )
            """)
            break
        except Exception as e:
            err_str = str(e)
            if ('is active for PID' in err_str or 'aborted' in err_str) and attempt < max_retries - 1:
                sleep_time = (0.5 + random.random()) * (attempt + 1)
                time.sleep(sleep_time)
                continue
            raise
    
    changes = []
    for row in cur.fetchall():
        data = row[0]
        if f'.{table_name}:' not in data and f'table {table_name}:' not in data:
            continue
        
        if 'table ' in data:
            if ': INSERT:' in data:
                action = 'I'
            elif ': UPDATE:' in data:
                action = 'U'
            elif ': DELETE:' in data:
                action = 'D'
            else:
                continue
            
            pk_match = re.search(rf'{pk_column}\[[\w]+\]:(\d+)', data)
            if pk_match:
                changes.append({
                    'action': action,
                    'pk': int(pk_match.group(1))
                })
    
    return changes


def _do_wal_load(session, connection_factory, source_schema: str, source_table: str,
                 full_target: str, pk_column: str, slot_name: str) -> tuple[int, int, str, int]:
    """
    WAL-based CDC - read changes from replication slot, fetch changed rows via DB-API, MERGE.
    
    Returns: (rows_processed, inserts+updates, deletes, mode_desc)
    """
    from snowflake.snowpark.functions import col, when_matched, when_not_matched
    import psycopg2
    
    conn = connection_factory()
    cur = conn.cursor()
    
    try:
        conn.rollback()  # Clear any aborted transaction state
        changes = _get_wal_changes(cur, slot_name, source_table, pk_column)
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        raise
    
    if not changes:
        cur.close()
        conn.close()
        return 0, 0, "WAL (no changes)", 0
    
    insert_update_pks = []
    delete_pks = []
    
    for change in changes:
        pk_val = change['pk']
        if pk_val is None:
            continue
        if change['action'] == 'D':
            delete_pks.append(pk_val)
        else:  # I or U
            insert_update_pks.append(pk_val)
    
    rows_merged = 0
    rows_deleted = 0
    
    if insert_update_pks:
        pk_list = ','.join(str(pk) for pk in insert_update_pks)
        query = f'SELECT * FROM "{source_schema}"."{source_table}" WHERE {pk_column} IN ({pk_list})'
        df = session.read.dbapi(connection_factory, query=query)
        
        if df.count() > 0:
            if not _table_exists(session, full_target):
                df.write.mode("overwrite").save_as_table(full_target)
                rows_merged = df.count()
            else:
                target_table = session.table(full_target)
                pk_cols = _parse_pk_columns(pk_column)
                pk_cols_upper = [c.upper() for c in pk_cols]
                
                merge_condition = None
                for pk_col in pk_cols_upper:
                    cond = target_table[pk_col] == df[pk_col]
                    merge_condition = cond if merge_condition is None else (merge_condition & cond)
                
                source_cols = [c for c in df.columns]
                update_assignments = {c: df[c] for c in source_cols if c.upper() not in pk_cols_upper}
                insert_assignments = {c: df[c] for c in source_cols}
                
                target_table.merge(
                    df,
                    merge_condition,
                    [
                        when_matched().update(update_assignments),
                        when_not_matched().insert(insert_assignments)
                    ]
                )
                rows_merged = len(insert_update_pks)
    
    if delete_pks and _table_exists(session, full_target):
        pk_list = ','.join(str(pk) for pk in delete_pks)
        session.sql(f'DELETE FROM {full_target} WHERE {pk_column.upper()} IN ({pk_list})').collect()
        rows_deleted = len(delete_pks)
    
    cur.execute(f"SELECT pg_logical_slot_get_changes('{slot_name}', NULL, {len(changes)})")
    cur.fetchall()  # consume results to release lock faster
    cur.close()
    conn.close()
    
    total = rows_merged + rows_deleted
    return total, rows_merged, f"WAL ({rows_merged} upserts, {rows_deleted} deletes)", rows_deleted


def sync_single_table(session, database_id: str, table_id: str) -> str:
    """
    Sync a single table from PostgreSQL to Snowflake.
    
    Supports three modes (configured in TABLE_REGISTRY.SYNC_METHOD):
    - 'full': Full table reload every sync
    - 'cdc': Incremental using CDC_COLUMN watermark + MERGE
    - 'wal': WAL-based CDC using PostgreSQL logical replication slot
    
    Args:
        session: Snowflake session (passed by Snowpark runtime)
        database_id: ID from DATABASE_REGISTRY
        table_id: ID from TABLE_REGISTRY
        
    Returns:
        Status message with sync results
    """
    import psycopg2
    
    start_time = time.time()
    user, password = _get_credentials()
    
    db_config = session.sql(f"""
        SELECT SOURCE_DB_NAME, TARGET_SCHEMA, SOURCE_SCHEMA, HOST, PORT 
        FROM DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY 
        WHERE DATABASE_ID = '{database_id}' AND IS_ACTIVE = TRUE
    """).collect()
    
    if not db_config:
        return f"Error: Database '{database_id}' not found or inactive"
    
    db = db_config[0]
    source_db = db['SOURCE_DB_NAME']
    target_schema = db['TARGET_SCHEMA']
    source_schema = db['SOURCE_SCHEMA'] or 'blfra'
    host = db['HOST']
    port = db['PORT'] or 5432
    
    tbl_config = session.sql(f"""
        SELECT TABLE_ID, SOURCE_TABLE, TARGET_TABLE, PRIMARY_KEY_COLUMN, 
               COALESCE(BATCH_SIZE, 100000) as BATCH_SIZE,
               COALESCE(SYNC_METHOD, 'full') as SYNC_METHOD,
               CDC_COLUMN,
               LAST_WATERMARK,
               WAL_SLOT_NAME
        FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
        WHERE TABLE_ID = '{table_id}' AND SYNC_ENABLED = TRUE
    """).collect()
    
    if not tbl_config:
        return f"Error: Table '{table_id}' not found or disabled"
    
    tbl = tbl_config[0]
    source_table = tbl['SOURCE_TABLE']
    target_table = tbl['TARGET_TABLE']
    pk_column = tbl['PRIMARY_KEY_COLUMN']
    batch_size = int(tbl['BATCH_SIZE'])
    sync_method = tbl['SYNC_METHOD'].lower() if tbl['SYNC_METHOD'] else 'full'
    cdc_column = tbl['CDC_COLUMN']
    last_watermark = tbl['LAST_WATERMARK']
    wal_slot_name = tbl['WAL_SLOT_NAME'] if tbl['WAL_SLOT_NAME'] else 'snowflake_cdc_slot'
    
    full_target = f"DBAPI_REPLICA_DB.{target_schema}.{target_table}"
    
    try:
        def connection_factory():
            return psycopg2.connect(
                host=host, port=port, dbname=source_db,
                user=user, password=password, sslmode='require'
            )
        
        conn = connection_factory()
        cur = conn.cursor()
        
        schema_changed, schema_msg = _handle_schema_evolution(
            session, cur, source_schema, source_table, full_target, table_id
        )
        
        cur.close()
        conn.close()
        
        force_full = schema_changed or not _table_exists(session, full_target)
        
        if sync_method == 'wal' and pk_column and not force_full:
            row_count, rows_merged, mode_desc, rows_deleted = _do_wal_load(
                session, connection_factory, source_schema, source_table,
                full_target, pk_column, wal_slot_name
            )
            watermark_update = ""
            cdc_rows_update = f", LAST_CDC_ROWS = {row_count}"
        elif sync_method == 'cdc' and cdc_column and pk_column and not force_full:
            row_count, batches_used, mode_desc, new_watermark = _do_cdc_load(
                session, connection_factory, source_schema, source_table,
                full_target, pk_column, cdc_column, last_watermark, batch_size
            )
            
            watermark_update = f", LAST_WATERMARK = '{new_watermark}'" if new_watermark else ""
            cdc_rows_update = f", LAST_CDC_ROWS = {row_count}"
        else:
            row_count, batches_used, mode_desc = _do_full_load(
                session, connection_factory, source_schema, source_table,
                full_target, pk_column, batch_size
            )
            if sync_method == 'cdc' and cdc_column:
                new_wm = session.sql(f'SELECT MAX("{cdc_column.upper()}") as wm FROM {full_target}').collect()[0]['WM']
                watermark_update = f", LAST_WATERMARK = '{new_wm}'" if new_wm else ""
            else:
                watermark_update = ""
            cdc_rows_update = ""
            if force_full and sync_method == 'cdc':
                mode_desc = "FULL (schema change)" if schema_changed else "FULL (initial)"
        
        duration = time.time() - start_time
        rows_per_sec = int(row_count / duration) if duration > 0 and row_count > 0 else 0
        
        new_watermark_val = watermark_update.replace(", LAST_WATERMARK = '", "").rstrip("'") if watermark_update else None
        session.sql(f"""
            INSERT INTO DBAPI_REPLICA_DB.UTILS.SYNC_LOG 
            (TABLE_ID, SYNC_STATUS, SYNC_RECORDS, SYNC_DURATION_SEC, NEW_WATERMARK, CDC_ROWS)
            VALUES ('{table_id}', 'success', {row_count}, {duration:.2f}, 
                    {f"'{new_watermark_val}'" if new_watermark_val else 'NULL'},
                    {row_count if cdc_rows_update else 'NULL'})
        """).collect()
        
        status_suffix = f" | {schema_msg}" if "evolved" in schema_msg or "initialized" in schema_msg else ""
        return f"SUCCESS [{mode_desc}]: {source_table} -> {target_table}: {row_count:,} rows in {duration:.1f}s ({rows_per_sec:,} rows/sec){status_suffix}"
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e).replace("'", "''")[:500]
        session.sql(f"""
            INSERT INTO DBAPI_REPLICA_DB.UTILS.SYNC_LOG 
            (TABLE_ID, SYNC_STATUS, SYNC_RECORDS, SYNC_DURATION_SEC, NEW_WATERMARK, CDC_ROWS)
            VALUES ('{table_id}', 'error: {error_msg}', 0, {duration:.2f}, NULL, NULL)
        """).collect()
        return f"ERROR: {source_table}: {str(e)[:200]}"


def check_pg_health(session) -> str:
    """
    Check PostgreSQL connection health and return metrics.
    
    Returns database size, replication slots, WAL lag, and active connections.
    """
    import psycopg2
    
    user, password = _get_credentials()
    
    db_config = session.sql("""
        SELECT HOST, SOURCE_DB_NAME FROM DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY 
        WHERE IS_ACTIVE = TRUE LIMIT 1
    """).collect()
    
    if not db_config:
        return "Error: No active database in registry"
    
    host = db_config[0]['HOST']
    dbname = db_config[0]['SOURCE_DB_NAME']
    
    conn = psycopg2.connect(
        host=host, port=5432, dbname=dbname,
        user=user, password=password, sslmode='require'
    )
    cur = conn.cursor()
    
    results = []
    
    cur.execute(f"SELECT pg_size_pretty(pg_database_size('{dbname}'))")
    results.append(f"Database Size: {cur.fetchone()[0]}")
    
    cur.execute("SHOW max_replication_slots")
    results.append(f"Max Replication Slots: {cur.fetchone()[0]}")
    
    cur.execute("SELECT COUNT(*) FROM pg_replication_slots")
    results.append(f"Current Slots Used: {cur.fetchone()[0]}")
    
    cur.execute("""
        SELECT COALESCE(pg_size_pretty(SUM(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn))), '0 bytes')
        FROM pg_replication_slots
    """)
    results.append(f"WAL Slot Lag: {cur.fetchone()[0]}")
    
    cur.execute("SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active'")
    results.append(f"Active Connections: {cur.fetchone()[0]}")
    
    cur.execute("SELECT slot_name, plugin FROM pg_replication_slots")
    slots = cur.fetchall()
    if slots:
        slot_list = ", ".join(f"{s[0]}({s[1]})" for s in slots)
        results.append(f"Slot Names: {slot_list}")
    
    cur.close()
    conn.close()
    
    return "\n".join(results)


def consolidate_sync_log(session) -> str:
    """
    Consolidate SYNC_LOG entries into TABLE_REGISTRY.
    
    This procedure should be called after all sync tasks complete.
    It takes the most recent sync log entry for each table and updates
    TABLE_REGISTRY with the results. This avoids lock contention during
    parallel task execution.
    
    Returns:
        Status message with count of tables updated
    """
    result = session.sql("""
        MERGE INTO DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY t
        USING (
            SELECT TABLE_ID, SYNC_STATUS, SYNC_RECORDS, NEW_WATERMARK, CDC_ROWS, LOGGED_AT
            FROM DBAPI_REPLICA_DB.UTILS.SYNC_LOG
            WHERE (TABLE_ID, LOGGED_AT) IN (
                SELECT TABLE_ID, MAX(LOGGED_AT)
                FROM DBAPI_REPLICA_DB.UTILS.SYNC_LOG
                GROUP BY TABLE_ID
            )
        ) s
        ON t.TABLE_ID = s.TABLE_ID
        WHEN MATCHED THEN UPDATE SET
            LAST_SYNC_AT = s.LOGGED_AT,
            LAST_SYNC_STATUS = s.SYNC_STATUS,
            LAST_SYNC_RECORDS = s.SYNC_RECORDS,
            LAST_WATERMARK = COALESCE(s.NEW_WATERMARK, t.LAST_WATERMARK),
            LAST_CDC_ROWS = COALESCE(s.CDC_ROWS, t.LAST_CDC_ROWS),
            UPDATED_AT = CURRENT_TIMESTAMP()
    """).collect()
    
    rows_updated = result[0]['number of rows updated'] if result else 0
    
    session.sql("TRUNCATE TABLE DBAPI_REPLICA_DB.UTILS.SYNC_LOG").collect()
    
    return f"Consolidated {rows_updated} sync log entries into TABLE_REGISTRY"


def register_table(session, database_id: str, source_table: str, 
                   sync_method: str = 'full', primary_key: str = 'id',
                   cdc_column: str = None, wal_slot: str = None) -> str:
    """
    Register a new table for replication.
    
    Args:
        database_id: ID from DATABASE_REGISTRY (e.g., 'blfra_prod')
        source_table: Table name in PostgreSQL (e.g., 'users')
        sync_method: 'full' (default), 'cdc', or 'wal'
        primary_key: Primary key column name (default: 'id')
        cdc_column: Timestamp column for CDC mode (required if sync_method='cdc')
        wal_slot: PostgreSQL replication slot name (required if sync_method='wal')
    
    Returns:
        Status message
    
    Example:
        -- Full sync (simplest)
        CALL REGISTER_TABLE('my_db', 'users', 'full', 'id', NULL, NULL);
        
        -- CDC with watermark
        CALL REGISTER_TABLE('my_db', 'orders', 'cdc', 'order_id', 'updated_at', NULL);
        
        -- WAL-based CDC
        CALL REGISTER_TABLE('my_db', 'transactions', 'wal', 'txn_id', NULL, 'my_slot');
    """
    db_config = session.sql(f"""
        SELECT TARGET_SCHEMA, SOURCE_SCHEMA 
        FROM DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY 
        WHERE DATABASE_ID = '{database_id}'
    """).collect()
    
    if not db_config:
        return f"Error: Database '{database_id}' not found in DATABASE_REGISTRY"
    
    target_schema = db_config[0]['TARGET_SCHEMA']
    source_schema = db_config[0]['SOURCE_SCHEMA'] or 'public'
    
    table_id = f"{database_id}_{source_table}"
    target_table = source_table.upper()
    
    existing = session.sql(f"""
        SELECT 1 FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY 
        WHERE TABLE_ID = '{table_id}'
    """).collect()
    
    if existing:
        session.sql(f"""
            UPDATE DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
            SET SYNC_METHOD = '{sync_method}',
                PRIMARY_KEY_COLUMN = '{primary_key}',
                CDC_COLUMN = {f"'{cdc_column}'" if cdc_column else 'NULL'},
                WAL_SLOT_NAME = {f"'{wal_slot}'" if wal_slot else 'NULL'},
                UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE TABLE_ID = '{table_id}'
        """).collect()
        return f"UPDATED: {table_id} -> sync_method='{sync_method}'"
    else:
        session.sql(f"""
            INSERT INTO DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
            (TABLE_ID, DATABASE_ID, SOURCE_SCHEMA, SOURCE_TABLE, TARGET_SCHEMA, 
             TARGET_TABLE, PRIMARY_KEY_COLUMN, SYNC_METHOD, CDC_COLUMN, WAL_SLOT_NAME)
            VALUES ('{table_id}', '{database_id}', '{source_schema}', '{source_table}',
                    '{target_schema}', '{target_table}', '{primary_key}', '{sync_method}',
                    {f"'{cdc_column}'" if cdc_column else 'NULL'},
                    {f"'{wal_slot}'" if wal_slot else 'NULL'})
        """).collect()
        return f"REGISTERED: {table_id} -> {target_schema}.{target_table} (sync_method='{sync_method}')"


def register_database(session, database_id: str, source_db_name: str, 
                      host: str, target_schema: str, 
                      source_schema: str = 'public', port: int = 5432) -> str:
    """
    Register a new source database for replication.
    
    Args:
        database_id: Unique identifier (e.g., 'customer_prod')
        source_db_name: PostgreSQL database name
        host: PostgreSQL host
        target_schema: Snowflake schema to replicate into
        source_schema: PostgreSQL schema (default: 'public')
        port: PostgreSQL port (default: 5432)
    
    Returns:
        Status message
    
    Example:
        CALL REGISTER_DATABASE('customer_prod', 'customer_db', 
            'myhost.postgres.snowflake.app', 'CUSTOMER_DATA', 'public', 5432);
    """
    existing = session.sql(f"""
        SELECT 1 FROM DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY 
        WHERE DATABASE_ID = '{database_id}'
    """).collect()
    
    if existing:
        session.sql(f"""
            UPDATE DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY
            SET SOURCE_DB_NAME = '{source_db_name}',
                HOST = '{host}',
                PORT = {port},
                TARGET_SCHEMA = '{target_schema}',
                SOURCE_SCHEMA = '{source_schema}',
                UPDATED_AT = CURRENT_TIMESTAMP()
            WHERE DATABASE_ID = '{database_id}'
        """).collect()
        return f"UPDATED: {database_id}"
    else:
        session.sql(f"""
            INSERT INTO DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY
            (DATABASE_ID, SOURCE_DB_NAME, HOST, PORT, TARGET_SCHEMA, SOURCE_SCHEMA, IS_ACTIVE)
            VALUES ('{database_id}', '{source_db_name}', '{host}', {port}, 
                    '{target_schema}', '{source_schema}', TRUE)
        """).collect()
        
        session.sql(f"CREATE SCHEMA IF NOT EXISTS DBAPI_REPLICA_DB.{target_schema}").collect()
        return f"REGISTERED: {database_id} -> {target_schema} (schema created)"


def list_tables(session, database_id: str = None) -> str:
    """
    List registered tables and their sync configuration.
    
    Args:
        database_id: Optional filter by database (shows all if NULL)
    
    Returns:
        Formatted table list
    """
    where_clause = f"WHERE DATABASE_ID = '{database_id}'" if database_id else ""
    
    tables = session.sql(f"""
        SELECT TABLE_ID, SOURCE_TABLE, SYNC_METHOD, SYNC_ENABLED, 
               LAST_SYNC_STATUS, LAST_SYNC_RECORDS
        FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
        {where_clause}
        ORDER BY DATABASE_ID, SOURCE_TABLE
    """).collect()
    
    if not tables:
        return "No tables registered" + (f" for database '{database_id}'" if database_id else "")
    
    lines = [f"{'TABLE_ID':<40} {'METHOD':<6} {'ENABLED':<8} {'STATUS':<10} {'ROWS':<10}"]
    lines.append("-" * 80)
    
    for t in tables:
        status = (t['LAST_SYNC_STATUS'] or 'never')[:10]
        rows = str(t['LAST_SYNC_RECORDS'] or 0)
        enabled = 'yes' if t['SYNC_ENABLED'] else 'no'
        lines.append(f"{t['TABLE_ID']:<40} {t['SYNC_METHOD']:<6} {enabled:<8} {status:<10} {rows:<10}")
    
    return "\n".join(lines)


def setup_replication(session, config_json: str) -> str:
    """
    Bulk setup replication from JSON configuration.
    Supports single database or multiple databases with shared table definitions.
    
    Args:
        config_json: JSON string with database(s) and table configuration
        
    JSON Format (Single Database):
    {
        "database": {"database_id": "prod", "source_db_name": "app", "host": "x.postgres.app", ...},
        "tables": [{"name": "users"}, {"name": "orders"}]
    }
    
    JSON Format (Multiple Databases - same tables):
    {
        "databases": [
            {"database_id": "customer_a", "source_db_name": "db_a", "host": "...", "target_schema": "CUST_A", "wal_slot": "slot_a"},
            {"database_id": "customer_b", "source_db_name": "db_b", "host": "...", "target_schema": "CUST_B", "wal_slot": "slot_b"}
        ],
        "defaults": {"sync_method": "full", "primary_key": "pkid"},
        "tables": [{"name": "users", "sync_method": "wal"}, {"name": "orders"}]
    }
    """
    import json
    
    try:
        config = json.loads(config_json)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON - {e}"
    
    results = []
    
    databases = config.get('databases', [])
    if not databases and config.get('database'):
        databases = [config.get('database')]
    
    if not databases:
        return "Error: 'database' or 'databases' configuration is required"
    
    defaults = config.get('defaults', {})
    default_sync = defaults.get('sync_method', 'full')
    default_pk = defaults.get('primary_key', 'id')
    default_cdc_col = defaults.get('cdc_column', 'db_update_date')
    default_wal_slot = defaults.get('wal_slot')
    
    tables = config.get('tables', [])
    
    for db_cfg in databases:
        database_id = db_cfg.get('database_id')
        if not database_id:
            results.append("DATABASE: Skipped (no database_id)")
            continue
        
        source_db = db_cfg.get('source_db_name', database_id)
        host = db_cfg.get('host')
        if not host:
            results.append(f"DATABASE: {database_id} skipped (no host)")
            continue
        
        port = db_cfg.get('port', 5432)
        source_schema = db_cfg.get('source_schema', 'public')
        target_schema = db_cfg.get('target_schema', database_id.upper())
        db_wal_slot = db_cfg.get('wal_slot', default_wal_slot)
        
        existing = session.sql(f"""
            SELECT 1 FROM DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY 
            WHERE DATABASE_ID = '{database_id}'
        """).collect()
        
        if existing:
            session.sql(f"""
                UPDATE DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY
                SET SOURCE_DB_NAME = '{source_db}', HOST = '{host}', PORT = {port},
                    TARGET_SCHEMA = '{target_schema}', SOURCE_SCHEMA = '{source_schema}',
                    UPDATED_AT = CURRENT_TIMESTAMP()
                WHERE DATABASE_ID = '{database_id}'
            """).collect()
            results.append(f"DATABASE: Updated {database_id} -> {target_schema}")
        else:
            session.sql(f"""
                INSERT INTO DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY
                (DATABASE_ID, SOURCE_DB_NAME, HOST, PORT, TARGET_SCHEMA, SOURCE_SCHEMA, IS_ACTIVE)
                VALUES ('{database_id}', '{source_db}', '{host}', {port}, 
                        '{target_schema}', '{source_schema}', TRUE)
            """).collect()
            session.sql(f"CREATE SCHEMA IF NOT EXISTS DBAPI_REPLICA_DB.{target_schema}").collect()
            results.append(f"DATABASE: Created {database_id} -> {target_schema}")
        
        for tbl in tables:
            name = tbl.get('name')
            if not name:
                continue
            
            sync_method = tbl.get('sync_method', default_sync)
            primary_key = tbl.get('primary_key', default_pk)
            cdc_column = tbl.get('cdc_column', default_cdc_col) if sync_method == 'cdc' else None
            wal_slot = db_wal_slot if sync_method == 'wal' else None
            
            table_id = f"{database_id}_{name}"
            target_table = name.upper()
            
            existing = session.sql(f"""
                SELECT 1 FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY 
                WHERE TABLE_ID = '{table_id}'
            """).collect()
            
            if existing:
                session.sql(f"""
                    UPDATE DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
                    SET SYNC_METHOD = '{sync_method}', PRIMARY_KEY_COLUMN = '{primary_key}',
                        CDC_COLUMN = {f"'{cdc_column}'" if cdc_column else 'NULL'},
                        WAL_SLOT_NAME = {f"'{wal_slot}'" if wal_slot else 'NULL'},
                        UPDATED_AT = CURRENT_TIMESTAMP()
                    WHERE TABLE_ID = '{table_id}'
                """).collect()
                results.append(f"  TABLE: Updated {name} ({sync_method})")
            else:
                session.sql(f"""
                    INSERT INTO DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
                    (TABLE_ID, DATABASE_ID, SOURCE_SCHEMA, SOURCE_TABLE, TARGET_SCHEMA, 
                     TARGET_TABLE, PRIMARY_KEY_COLUMN, SYNC_METHOD, CDC_COLUMN, WAL_SLOT_NAME, SYNC_ENABLED)
                    VALUES ('{table_id}', '{database_id}', '{source_schema}', '{name}',
                            '{target_schema}', '{target_table}', '{primary_key}', '{sync_method}',
                            {f"'{cdc_column}'" if cdc_column else 'NULL'},
                            {f"'{wal_slot}'" if wal_slot else 'NULL'}, TRUE)
                """).collect()
                results.append(f"  TABLE: Created {name} ({sync_method})")
    
    results.append(f"\nTotal: {len(databases)} database(s), {len(tables)} table(s) per database")
    return "\n".join(results)


def test_wal_cdc(session, action: str, table_name: str = 'users') -> str:
    """
    Test WAL CDC by making a change in PostgreSQL and returning what's in the WAL.
    
    Args:
        action: 'insert', 'update', 'delete', or 'peek' (just look at WAL without changes)
        table_name: Table to modify (default: users)
    
    Returns:
        Status message showing what was done and what's in the WAL
    """
    import psycopg2
    import re
    
    user, password = _get_credentials()
    
    db_config = session.sql("""
        SELECT HOST, SOURCE_DB_NAME, SOURCE_SCHEMA 
        FROM DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY 
        WHERE IS_ACTIVE = TRUE LIMIT 1
    """).collect()
    
    if not db_config:
        return "Error: No active database in registry"
    
    host = db_config[0]['HOST']
    dbname = db_config[0]['SOURCE_DB_NAME']
    schema = db_config[0]['SOURCE_SCHEMA'] or 'blfra'
    
    conn = psycopg2.connect(
        host=host, port=5432, dbname=dbname,
        user=user, password=password, sslmode='require'
    )
    cur = conn.cursor()
    
    results = []
    action = action.lower()
    
    if action == 'insert':
        cur.execute(f"""
            INSERT INTO "{schema}"."{table_name}" (full_name, email, db_insert_date, db_update_date)
            VALUES ('WAL Test User', 'wal_test@example.com', NOW(), NOW())
            RETURNING pkid
        """)
        new_id = cur.fetchone()[0]
        conn.commit()
        results.append(f"INSERTED: pkid={new_id} into {table_name}")
        
    elif action == 'update':
        cur.execute(f"""
            UPDATE "{schema}"."{table_name}" 
            SET full_name = 'WAL Updated ' || NOW()::text, db_update_date = NOW()
            WHERE pkid = (SELECT MAX(pkid) FROM "{schema}"."{table_name}")
            RETURNING pkid
        """)
        row = cur.fetchone()
        if row:
            conn.commit()
            results.append(f"UPDATED: pkid={row[0]} in {table_name}")
        else:
            results.append("No rows to update")
            
    elif action == 'delete':
        cur.execute(f"""
            DELETE FROM "{schema}"."{table_name}" 
            WHERE email = 'wal_test@example.com'
            RETURNING pkid
        """)
        rows = cur.fetchall()
        conn.commit()
        if rows:
            results.append(f"DELETED: pkids={[r[0] for r in rows]} from {table_name}")
        else:
            results.append("No test rows to delete")
            
    elif action == 'peek':
        results.append("PEEK mode - no changes made")
    else:
        return f"Error: Unknown action '{action}'. Use 'insert', 'update', 'delete', or 'peek'"
    
    cur.execute("""
        SELECT data FROM pg_logical_slot_peek_changes('sf_cdc_blfra_db', NULL, 100)
    """)
    wal_data = cur.fetchall()
    
    table_changes = []
    for row in wal_data:
        data = row[0]
        if f'table {table_name}:' in data or f'table {schema}.{table_name}:' in data:
            if len(data) > 100:
                data = data[:100] + '...'
            table_changes.append(data)
    
    results.append(f"\nWAL changes for {table_name} ({len(table_changes)} found):")
    for i, change in enumerate(table_changes[:10]):
        results.append(f"  {i+1}. {change}")
    if len(table_changes) > 10:
        results.append(f"  ... and {len(table_changes) - 10} more")
    
    cur.close()
    conn.close()
    
    return "\n".join(results)
