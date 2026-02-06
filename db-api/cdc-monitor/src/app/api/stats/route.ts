import { NextResponse } from 'next/server'
import { executeQuery } from '@/lib/snowflake'

export const dynamic = 'force-dynamic'

export async function GET() {
  try {
    const hourlyStats = await executeQuery(`
      SELECT 
        DATE_TRUNC('hour', LOGGED_AT) as hour,
        COUNT(*) as total_syncs,
        SUM(CASE WHEN SYNC_STATUS = 'success' THEN 1 ELSE 0 END) as successful,
        SUM(CASE WHEN SYNC_STATUS LIKE 'error%' THEN 1 ELSE 0 END) as errors,
        SUM(COALESCE(SYNC_RECORDS, 0)) as total_rows,
        AVG(SYNC_DURATION_SEC) as avg_duration
      FROM DBAPI_REPLICA_DB.UTILS.SYNC_LOG
      WHERE LOGGED_AT > DATEADD('hour', -24, CURRENT_TIMESTAMP())
      GROUP BY DATE_TRUNC('hour', LOGGED_AT)
      ORDER BY hour DESC
    `);

    const tableStats = await executeQuery(`
      SELECT 
        TABLE_ID,
        LAST_SYNC_STATUS,
        LAST_SYNC_RECORDS,
        LAST_SYNC_AT,
        SYNC_METHOD
      FROM DBAPI_REPLICA_DB.UTILS.TABLE_REGISTRY
      WHERE SYNC_ENABLED = TRUE
      ORDER BY LAST_SYNC_AT DESC NULLS LAST
    `);

    return NextResponse.json({ hourlyStats, tableStats })
  } catch (error) {
    console.error('Stats API error:', error);
    return NextResponse.json({ error: String(error) }, { status: 500 })
  }
}
