import { NextResponse } from 'next/server'
import { executeQuery } from '@/lib/snowflake'

export const dynamic = 'force-dynamic'

export async function POST() {
  try {
    await executeQuery('EXECUTE TASK DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG')
    return NextResponse.json({ success: true, message: 'Sync triggered' })
  } catch (error) {
    return NextResponse.json({ success: false, error: String(error) }, { status: 500 })
  }
}
