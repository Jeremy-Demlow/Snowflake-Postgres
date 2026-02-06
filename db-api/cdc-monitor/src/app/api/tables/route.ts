import { NextResponse } from 'next/server'
import { executeQuery } from '@/lib/snowflake'

export const dynamic = 'force-dynamic'

export async function GET() {
  const tables = await executeQuery(`
    SELECT t.TABLE_ID, t.SOURCE_TABLE, t.TARGET_TABLE, t.SYNC_METHOD, 
           t.SYNC_ENABLED, t.WAL_SLOT_NAME, t.CDC_COLUMN,
           d.DATABASE_ID, d.SOURCE_DB_NAME, d.TARGET_SCHEMA
    FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY t
    JOIN DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY d 
      ON t.DATABASE_ID = d.DATABASE_ID
    ORDER BY d.DATABASE_ID, t.SOURCE_TABLE
  `)
  
  return NextResponse.json({ tables })
}
