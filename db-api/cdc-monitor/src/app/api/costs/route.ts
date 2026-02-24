import { NextResponse } from 'next/server'
import { executeQuery } from '@/lib/snowflake'

export const dynamic = 'force-dynamic'

export async function GET() {
  const [warehouseCosts, dailyCosts, projectedCosts, costByDatabase, costByTable, throughputStats] = await Promise.all([
    executeQuery(`
      SELECT 
        WAREHOUSE_NAME,
        ROUND(SUM(CREDITS_USED), 4) as TOTAL_CREDITS,
        ROUND(SUM(CREDITS_USED_COMPUTE), 4) as COMPUTE_CREDITS,
        ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 4) as CLOUD_CREDITS,
        ROUND(SUM(CREDITS_USED) * 3, 2) as EST_COST_USD,
        COUNT(DISTINCT DATE_TRUNC('hour', START_TIME)) as ACTIVE_HOURS
      FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
      WHERE WAREHOUSE_NAME = 'CDC_PIPELINE_WH'
        AND START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
      GROUP BY WAREHOUSE_NAME
    `),
    executeQuery(`
      SELECT 
        DATE_TRUNC('day', START_TIME)::DATE as DAY,
        ROUND(SUM(CREDITS_USED), 4) as CREDITS,
        ROUND(SUM(CREDITS_USED_COMPUTE), 4) as COMPUTE_CREDITS,
        ROUND(SUM(CREDITS_USED_CLOUD_SERVICES), 4) as CLOUD_CREDITS,
        ROUND(SUM(CREDITS_USED) * 3, 2) as COST_USD
      FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
      WHERE WAREHOUSE_NAME = 'CDC_PIPELINE_WH'
        AND START_TIME >= DATEADD('day', -14, CURRENT_TIMESTAMP())
      GROUP BY 1
      ORDER BY 1 DESC
    `),
    executeQuery(`
      SELECT 
        COUNT(DISTINCT TABLE_ID) as TABLE_COUNT,
        COUNT(*) as SYNC_COUNT_30D,
        ROUND(COUNT(*) / 30.0, 1) as AVG_SYNCS_PER_DAY,
        ROUND(AVG(SYNC_DURATION_SEC), 2) as AVG_SYNC_DURATION,
        SUM(SYNC_RECORDS) as TOTAL_ROWS_SYNCED
      FROM DBAPI_REPLICA_DB.UTILS.SYNC_HISTORY
      WHERE LOGGED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    `),
    executeQuery(`
      SELECT 
        DATABASE_ID,
        COUNT(DISTINCT TABLE_ID) as TABLE_COUNT,
        COUNT(*) as SYNC_COUNT,
        SUM(SYNC_RECORDS) as TOTAL_ROWS,
        ROUND(AVG(SYNC_DURATION_SEC), 2) as AVG_DURATION_SEC,
        ROUND(AVG(ROWS_PER_SEC), 0) as AVG_THROUGHPUT
      FROM DBAPI_REPLICA_DB.UTILS.SYNC_HISTORY
      WHERE LOGGED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
        AND DATABASE_ID IS NOT NULL
      GROUP BY DATABASE_ID
      ORDER BY TOTAL_ROWS DESC
    `),
    executeQuery(`
      SELECT 
        TABLE_ID,
        DATABASE_ID,
        COUNT(*) as SYNC_COUNT,
        SUM(SYNC_RECORDS) as TOTAL_ROWS,
        ROUND(AVG(SYNC_DURATION_SEC), 2) as AVG_DURATION_SEC,
        ROUND(AVG(ROWS_PER_SEC), 0) as AVG_THROUGHPUT,
        MAX(SYNC_RECORDS) as MAX_ROWS_SINGLE_SYNC
      FROM DBAPI_REPLICA_DB.UTILS.SYNC_HISTORY
      WHERE LOGGED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
        AND SYNC_RECORDS > 0
      GROUP BY TABLE_ID, DATABASE_ID
      ORDER BY TOTAL_ROWS DESC
      LIMIT 20
    `),
    executeQuery(`
      SELECT 
        ROUND(AVG(CASE WHEN ROWS_PER_SEC > 0 THEN ROWS_PER_SEC END), 0) as AVG_THROUGHPUT,
        ROUND(MAX(ROWS_PER_SEC), 0) as MAX_THROUGHPUT,
        ROUND(MIN(CASE WHEN ROWS_PER_SEC > 0 THEN ROWS_PER_SEC END), 0) as MIN_THROUGHPUT,
        ROUND(AVG(SYNC_DURATION_SEC), 2) as AVG_DURATION,
        SUM(SYNC_RECORDS) as TOTAL_ROWS_SYNCED,
        COUNT(*) as TOTAL_SYNCS
      FROM DBAPI_REPLICA_DB.UTILS.SYNC_HISTORY
      WHERE LOGGED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    `)
  ])

  const summary = warehouseCosts[0] || { TOTAL_CREDITS: 0, COMPUTE_CREDITS: 0, CLOUD_CREDITS: 0, EST_COST_USD: 0, ACTIVE_HOURS: 0 }
  const projection = projectedCosts[0] || { TABLE_COUNT: 0, SYNC_COUNT_30D: 0, AVG_SYNCS_PER_DAY: 0, TOTAL_ROWS_SYNCED: 0 }
  const throughput = throughputStats[0] || { AVG_THROUGHPUT: 0, MAX_THROUGHPUT: 0, TOTAL_ROWS_SYNCED: 0 }
  
  const totalCredits = Number(summary.TOTAL_CREDITS) || 0
  const computeCredits = Number(summary.COMPUTE_CREDITS) || 0
  const cloudCredits = Number(summary.CLOUD_CREDITS) || 0
  const syncCount = Number(projection.SYNC_COUNT_30D) || 0
  const creditsPerSync = totalCredits && syncCount 
    ? (totalCredits / syncCount)
    : 0

  const avgSyncsPerDay = Number(projection.AVG_SYNCS_PER_DAY) || 0
  const avgThroughput = Number(throughput.AVG_THROUGHPUT) || 5000
  const avgDuration = Number(projection.AVG_SYNC_DURATION) || 5
  
  const estCreditsPerCycleAtScale = 2000 * (avgDuration / 3600) * (1/12)

  return NextResponse.json({
    summary: {
      totalCredits: totalCredits,
      computeCredits: computeCredits,
      cloudCredits: cloudCredits,
      estCostUsd: Number(summary.EST_COST_USD) || 0,
      activeHours: Number(summary.ACTIVE_HOURS) || 0,
      tableCount: Number(projection.TABLE_COUNT) || 0,
      syncCount30d: syncCount,
      avgSyncsPerDay: avgSyncsPerDay,
      creditsPerSync: creditsPerSync,
      totalRowsSynced: Number(projection.TOTAL_ROWS_SYNCED) || 0
    },
    throughput: {
      avgRowsPerSec: avgThroughput,
      maxRowsPerSec: Number(throughput.MAX_THROUGHPUT) || 0,
      minRowsPerSec: Number(throughput.MIN_THROUGHPUT) || 0,
      avgDurationSec: avgDuration,
      totalRowsSynced: Number(throughput.TOTAL_ROWS_SYNCED) || 0,
      totalSyncs: Number(throughput.TOTAL_SYNCS) || 0
    },
    dailyCosts,
    costByDatabase,
    costByTable,
    projections: {
      currentScale: {
        tables: Number(projection.TABLE_COUNT) || 0,
        syncsPerMonth: Math.round(avgSyncsPerDay * 30),
        estMonthlyCredits: Math.round(avgSyncsPerDay * 30 * creditsPerSync * 100) / 100,
        estMonthlyCost: Math.round(avgSyncsPerDay * 30 * creditsPerSync * 3)
      },
      atScale: {
        tables: 2000,
        syncsPerDay: 96,
        estCreditsPerCycle: Math.round(estCreditsPerCycleAtScale * 100) / 100 || 3,
        estMonthlyCredits: Math.round(96 * 30 * (estCreditsPerCycleAtScale || 3)),
        estMonthlyCost: Math.round(96 * 30 * (estCreditsPerCycleAtScale || 3) * 3)
      }
    },
    warehouseConfig: {
      name: 'CDC_PIPELINE_WH',
      type: 'Multi-Cluster Warehouse (MCW)',
      size: 'X-Small',
      minClusters: 1,
      maxClusters: 12,
      autoSuspend: 60,
      scalingPolicy: 'STANDARD'
    }
  })
}
