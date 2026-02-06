import { NextResponse } from 'next/server'
import { executeQuery } from '@/lib/snowflake'

export const dynamic = 'force-dynamic'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const limit = parseInt(searchParams.get('limit') || '100')
  const status = searchParams.get('status') || 'all'
  const table = searchParams.get('table') || ''
  
  let whereClause = '1=1'
  if (status === 'success') whereClause += " AND SYNC_STATUS = 'success'"
  if (status === 'error') whereClause += " AND SYNC_STATUS LIKE 'error%'"
  if (table) whereClause += ` AND TABLE_ID LIKE '%${table}%'`
  
  const logs = await executeQuery(`
    SELECT LOG_ID, TABLE_ID, SYNC_STATUS, SYNC_RECORDS, 
           ROUND(SYNC_DURATION_SEC, 2) as SYNC_DURATION_SEC, 
           NEW_WATERMARK, CDC_ROWS, LOGGED_AT
    FROM DBAPI_REPLICA_DB.UTILS.SYNC_LOG
    WHERE ${whereClause}
    ORDER BY LOGGED_AT DESC
    LIMIT ${limit}
  `)
  
  return NextResponse.json({ logs })
}
