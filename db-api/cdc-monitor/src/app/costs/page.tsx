'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { ArrowLeft, DollarSign, TrendingUp, Activity, RefreshCw, Database, Zap, Server } from 'lucide-react'

interface CostData {
  summary: {
    totalCredits: number
    computeCredits: number
    cloudCredits: number
    estCostUsd: number
    activeHours: number
    tableCount: number
    syncCount30d: number
    avgSyncsPerDay: number
    creditsPerSync: number
    totalRowsSynced: number
  }
  throughput: {
    avgRowsPerSec: number
    maxRowsPerSec: number
    minRowsPerSec: number
    avgDurationSec: number
    totalRowsSynced: number
    totalSyncs: number
  }
  dailyCosts: Array<{ DAY: string; CREDITS: number; COMPUTE_CREDITS: number; CLOUD_CREDITS: number; COST_USD: number }>
  costByDatabase: Array<{ DATABASE_ID: string; TABLE_COUNT: number; SYNC_COUNT: number; TOTAL_ROWS: number; AVG_DURATION_SEC: number; AVG_THROUGHPUT: number }>
  costByTable: Array<{ TABLE_ID: string; DATABASE_ID: string; SYNC_COUNT: number; TOTAL_ROWS: number; AVG_DURATION_SEC: number; AVG_THROUGHPUT: number; MAX_ROWS_SINGLE_SYNC: number }>
  projections: {
    currentScale: {
      tables: number
      syncsPerMonth: number
      estMonthlyCredits: number
      estMonthlyCost: number
    }
    atScale: {
      tables: number
      syncsPerDay: number
      estCreditsPerCycle: number
      estMonthlyCredits: number
      estMonthlyCost: number
    }
  }
  warehouseConfig: {
    name: string
    type: string
    size: string
    minClusters: number
    maxClusters: number
    autoSuspend: number
    scalingPolicy: string
  }
}

export default function CostsPage() {
  const [costs, setCosts] = useState<CostData | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'overview' | 'database' | 'table'>('overview')

  const fetchCosts = async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/costs')
      const data = await res.json()
      setCosts(data)
    } catch (err) {
      console.error('Failed to fetch costs:', err)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchCosts()
  }, [])

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="max-w-7xl mx-auto p-8">
        <div className="flex items-center gap-4 mb-8">
          <Link href="/" className="p-2 hover:bg-gray-800 rounded transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div className="flex-1">
            <h1 className="text-3xl font-bold">Cost Tracking</h1>
            <p className="text-gray-400">CDC_PIPELINE_WH credit usage and projections</p>
          </div>
          <button
            onClick={fetchCosts}
            className="p-2 hover:bg-gray-800 rounded transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {loading && !costs ? (
          <div className="text-center py-20 text-gray-400">
            <RefreshCw className="w-10 h-10 animate-spin mx-auto mb-4" />
            Loading cost data...
          </div>
        ) : costs ? (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
              <div className="p-5 bg-gray-900 rounded-lg border border-gray-800">
                <DollarSign className="w-5 h-5 text-yellow-400 mb-2" />
                <div className="text-xs text-gray-400">30-Day Credits</div>
                <div className="text-2xl font-bold text-yellow-400">{costs.summary.totalCredits.toFixed(2)}</div>
                <div className="text-xs text-gray-500 mt-1">
                  Compute: {costs.summary.computeCredits.toFixed(2)} | Cloud: {costs.summary.cloudCredits.toFixed(2)}
                </div>
              </div>
              <div className="p-5 bg-gray-900 rounded-lg border border-gray-800">
                <DollarSign className="w-5 h-5 text-green-400 mb-2" />
                <div className="text-xs text-gray-400">30-Day Cost</div>
                <div className="text-2xl font-bold text-green-400">${costs.summary.estCostUsd.toFixed(2)}</div>
                <div className="text-xs text-gray-500 mt-1">@ $3/credit</div>
              </div>
              <div className="p-5 bg-gray-900 rounded-lg border border-gray-800">
                <Zap className="w-5 h-5 text-cyan-400 mb-2" />
                <div className="text-xs text-gray-400">Avg Throughput</div>
                <div className="text-2xl font-bold text-cyan-400">{costs.throughput.avgRowsPerSec.toLocaleString()}</div>
                <div className="text-xs text-gray-500 mt-1">rows/sec</div>
              </div>
              <div className="p-5 bg-gray-900 rounded-lg border border-gray-800">
                <Activity className="w-5 h-5 text-blue-400 mb-2" />
                <div className="text-xs text-gray-400">Total Rows</div>
                <div className="text-2xl font-bold text-blue-400">{(costs.throughput.totalRowsSynced / 1e6).toFixed(1)}M</div>
                <div className="text-xs text-gray-500 mt-1">{costs.throughput.totalSyncs.toLocaleString()} syncs</div>
              </div>
              <div className="p-5 bg-gray-900 rounded-lg border border-gray-800">
                <TrendingUp className="w-5 h-5 text-purple-400 mb-2" />
                <div className="text-xs text-gray-400">Cost/Sync</div>
                <div className="text-2xl font-bold text-purple-400">${(costs.summary.creditsPerSync * 3).toFixed(4)}</div>
                <div className="text-xs text-gray-500 mt-1">{costs.summary.creditsPerSync.toFixed(4)} credits</div>
              </div>
            </div>

            <div className="flex gap-2 mb-6">
              <button
                onClick={() => setActiveTab('overview')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === 'overview' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setActiveTab('database')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === 'database' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                By Database
              </button>
              <button
                onClick={() => setActiveTab('table')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === 'table' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                Top Tables
              </button>
            </div>

            {activeTab === 'overview' && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                  <div className="p-6 bg-gray-900 rounded-lg border border-gray-800">
                    <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                      <Server className="w-5 h-5 text-blue-400" />
                      Current Scale
                    </h3>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Tables Monitored</span>
                        <span className="font-mono">{costs.summary.tableCount}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Syncs (30 days)</span>
                        <span className="font-mono">{costs.summary.syncCount30d.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Avg Syncs/Day</span>
                        <span className="font-mono">{costs.summary.avgSyncsPerDay}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Avg Duration</span>
                        <span className="font-mono">{costs.throughput.avgDurationSec.toFixed(1)}s</span>
                      </div>
                      <hr className="border-gray-700" />
                      <div className="flex justify-between text-lg">
                        <span className="text-gray-400">Est. Monthly Cost</span>
                        <span className="font-bold text-green-400">${costs.projections.currentScale.estMonthlyCost}</span>
                      </div>
                    </div>
                  </div>

                  <div className="p-6 bg-gray-900 rounded-lg border border-yellow-800">
                    <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-yellow-400" />
                      At Scale (50 DBs × 40 Tables)
                    </h3>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Tables</span>
                        <span className="font-mono">{costs.projections.atScale.tables.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Syncs/Day (15-min)</span>
                        <span className="font-mono">{costs.projections.atScale.syncsPerDay}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Est. Credits/Cycle</span>
                        <span className="font-mono">{costs.projections.atScale.estCreditsPerCycle}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Monthly Credits</span>
                        <span className="font-mono">{costs.projections.atScale.estMonthlyCredits.toLocaleString()}</span>
                      </div>
                      <hr className="border-gray-700" />
                      <div className="flex justify-between text-lg">
                        <span className="text-gray-400">Est. Monthly Cost</span>
                        <span className="font-bold text-yellow-400">${costs.projections.atScale.estMonthlyCost.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="p-6 bg-gray-900 rounded-lg border border-gray-800 mb-6">
                  <h3 className="text-lg font-semibold mb-4">Daily Usage (CDC_PIPELINE_WH)</h3>
                  {costs.dailyCosts.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-gray-400 border-b border-gray-700">
                            <th className="text-left py-2">Date</th>
                            <th className="text-right py-2">Total Credits</th>
                            <th className="text-right py-2">Compute</th>
                            <th className="text-right py-2">Cloud Services</th>
                            <th className="text-right py-2">Est. Cost</th>
                          </tr>
                        </thead>
                        <tbody>
                          {costs.dailyCosts.map((day, i) => (
                            <tr key={i} className="border-b border-gray-800">
                              <td className="py-2 font-mono">{day.DAY}</td>
                              <td className="text-right py-2 text-yellow-400">{day.CREDITS?.toFixed(4) || '0'}</td>
                              <td className="text-right py-2 text-blue-400">{day.COMPUTE_CREDITS?.toFixed(4) || '0'}</td>
                              <td className="text-right py-2 text-purple-400">{day.CLOUD_CREDITS?.toFixed(4) || '0'}</td>
                              <td className="text-right py-2 text-green-400">${day.COST_USD?.toFixed(2) || '0.00'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-gray-500 text-center py-8">No usage data for CDC_PIPELINE_WH yet</p>
                  )}
                </div>

                <div className="p-4 bg-gray-800 rounded-lg">
                  <h4 className="text-sm font-medium text-gray-400 mb-2 flex items-center gap-2">
                    <Database className="w-4 h-4" />
                    Warehouse Configuration
                  </h4>
                  <div className="text-sm text-gray-300">
                    <span className="font-mono text-blue-400">{costs.warehouseConfig.name}</span> — {costs.warehouseConfig.type}, {costs.warehouseConfig.size} size, {costs.warehouseConfig.minClusters}-{costs.warehouseConfig.maxClusters} clusters, {costs.warehouseConfig.autoSuspend}s auto-suspend
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    MCW enables horizontal scaling: all sync tasks run in parallel across up to {costs.warehouseConfig.maxClusters} clusters. 
                    At 50 DBs × 40 tables = 2,000 syncs, no queueing occurs.
                  </p>
                </div>
              </>
            )}

            {activeTab === 'database' && (
              <div className="p-6 bg-gray-900 rounded-lg border border-gray-800">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Database className="w-5 h-5 text-blue-400" />
                  Cost by Database (30 Days)
                </h3>
                {costs.costByDatabase && costs.costByDatabase.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-gray-400 border-b border-gray-700">
                          <th className="text-left py-2">Database</th>
                          <th className="text-right py-2">Tables</th>
                          <th className="text-right py-2">Syncs</th>
                          <th className="text-right py-2">Total Rows</th>
                          <th className="text-right py-2">Avg Duration</th>
                          <th className="text-right py-2">Avg Throughput</th>
                        </tr>
                      </thead>
                      <tbody>
                        {costs.costByDatabase.map((db, i) => (
                          <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                            <td className="py-2 font-mono text-blue-400">{db.DATABASE_ID || 'unknown'}</td>
                            <td className="text-right py-2">{db.TABLE_COUNT}</td>
                            <td className="text-right py-2">{db.SYNC_COUNT?.toLocaleString()}</td>
                            <td className="text-right py-2 text-yellow-400">{db.TOTAL_ROWS?.toLocaleString()}</td>
                            <td className="text-right py-2">{db.AVG_DURATION_SEC?.toFixed(1)}s</td>
                            <td className="text-right py-2 text-cyan-400">{db.AVG_THROUGHPUT?.toLocaleString()} rows/s</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-gray-500 text-center py-8">No database breakdown available</p>
                )}
              </div>
            )}

            {activeTab === 'table' && (
              <div className="p-6 bg-gray-900 rounded-lg border border-gray-800">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Activity className="w-5 h-5 text-purple-400" />
                  Top 20 Tables by Volume (30 Days)
                </h3>
                {costs.costByTable && costs.costByTable.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-gray-400 border-b border-gray-700">
                          <th className="text-left py-2">Table</th>
                          <th className="text-right py-2">Syncs</th>
                          <th className="text-right py-2">Total Rows</th>
                          <th className="text-right py-2">Max/Sync</th>
                          <th className="text-right py-2">Avg Duration</th>
                          <th className="text-right py-2">Throughput</th>
                        </tr>
                      </thead>
                      <tbody>
                        {costs.costByTable.map((table, i) => (
                          <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                            <td className="py-2">
                              <div className="font-mono text-sm text-white">{table.TABLE_ID?.split('.').pop()}</div>
                              <div className="text-xs text-gray-500">{table.DATABASE_ID}</div>
                            </td>
                            <td className="text-right py-2">{table.SYNC_COUNT}</td>
                            <td className="text-right py-2 text-yellow-400">{table.TOTAL_ROWS?.toLocaleString()}</td>
                            <td className="text-right py-2 text-orange-400">{table.MAX_ROWS_SINGLE_SYNC?.toLocaleString()}</td>
                            <td className="text-right py-2">{table.AVG_DURATION_SEC?.toFixed(1)}s</td>
                            <td className="text-right py-2 text-cyan-400">{table.AVG_THROUGHPUT?.toLocaleString()} rows/s</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-gray-500 text-center py-8">No table breakdown available</p>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-20 text-gray-400">
            Failed to load cost data
          </div>
        )}
      </div>
    </main>
  )
}
