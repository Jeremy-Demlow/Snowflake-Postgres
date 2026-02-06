import { NextResponse } from 'next/server'
import { testConnection, executeQuery } from '@/lib/snowflake'

export const dynamic = 'force-dynamic'

export async function GET() {
  const result = await testConnection();
  
  if (!result.connected) {
    return NextResponse.json({
      status: 'error',
      snowflake: { connected: false, error: result.error },
      timestamp: new Date().toISOString()
    }, { status: 503 })
  }

  try {
    const stats = await executeQuery<{ databases: number; tables: number; synced: number; total_rows: number }>(`
      SELECT 
        (SELECT COUNT(*) FROM DBAPI_REPLICA_DB.UTILS.DATABASE_REGISTRY WHERE IS_ACTIVE = TRUE) as databases,
        (SELECT COUNT(*) FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY WHERE SYNC_ENABLED = TRUE) as tables,
        (SELECT COUNT(*) FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY WHERE LAST_SYNC_STATUS = 'success') as synced,
        (SELECT COALESCE(SUM(LAST_SYNC_RECORDS), 0) FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY) as total_rows
    `);

    return NextResponse.json({
      status: 'ok',
      snowflake: { connected: true },
      stats: stats[0] || { databases: 0, tables: 0, synced: 0, total_rows: 0 },
      timestamp: new Date().toISOString()
    })
  } catch (err) {
    return NextResponse.json({
      status: 'partial',
      snowflake: { connected: true },
      error: (err as Error).message,
      timestamp: new Date().toISOString()
    })
  }
}
