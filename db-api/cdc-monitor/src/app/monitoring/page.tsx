'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { ArrowLeft, RefreshCw, Play, CheckCircle, XCircle, Clock, TrendingUp, Database, Loader2 } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts'

interface SyncLog {
  LOG_ID: number
  TABLE_ID: string
  SYNC_STATUS: string
  SYNC_RECORDS: number
  SYNC_DURATION_SEC: number
  LOGGED_AT: string
}

interface TableStat {
  TABLE_ID: string
  LAST_SYNC_STATUS: string
  LAST_SYNC_RECORDS: number
  LAST_SYNC_AT: string
  SYNC_METHOD: string
}

interface HourlyStat {
  HOUR: string
  TOTAL_SYNCS: number
  SUCCESSFUL: number
  ERRORS: number
  TOTAL_ROWS: number
  AVG_DURATION: number
}

export default function MonitoringPage() {
  const [logs, setLogs] = useState<SyncLog[]>([])
  const [tableStats, setTableStats] = useState<TableStat[]>([])
  const [hourlyStats, setHourlyStats] = useState<HourlyStat[]>([])
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [activeTab, setActiveTab] = useState<'recent' | 'tables' | 'charts'>('recent')

  const fetchData = async () => {
    setLoading(true)
    try {
      const [logsRes, statsRes] = await Promise.all([
        fetch('/api/sync-logs?limit=50'),
        fetch('/api/stats')
      ])
      const logsData = await logsRes.json()
      const statsData = await statsRes.json()
      
      setLogs(logsData.logs || [])
      setTableStats(statsData.tableStats || [])
      setHourlyStats(statsData.hourlyStats || [])
    } catch (err) {
      console.error('Failed to fetch data:', err)
    }
    setLoading(false)
  }

  const triggerSync = async () => {
    setTriggering(true)
    try {
      await fetch('/api/trigger-sync', { method: 'POST' })
      setTimeout(() => {
        setTriggering(false)
        fetchData()
      }, 3000)
    } catch (err) {
      setTriggering(false)
    }
  }

  useEffect(() => {
    fetchData()
    if (autoRefresh) {
      const interval = setInterval(fetchData, 10000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh])

  const successCount = logs.filter(l => l.SYNC_STATUS === 'success').length
  const errorCount = logs.filter(l => l.SYNC_STATUS?.startsWith('error')).length
  const totalRows = logs.reduce((acc, l) => acc + (l.SYNC_RECORDS || 0), 0)

  const chartData = [...hourlyStats].reverse().map(h => ({
    hour: new Date(h.HOUR).toLocaleTimeString('en-US', { hour: 'numeric' }),
    rows: h.TOTAL_ROWS,
    syncs: h.TOTAL_SYNCS,
    errors: h.ERRORS,
    duration: Math.round(h.AVG_DURATION || 0)
  }))

  const getSyncMethodColor = (method: string) => {
    switch (method?.toLowerCase()) {
      case 'cdc': return 'text-green-400'
      case 'wal': return 'text-purple-400'
      default: return 'text-blue-400'
    }
  }

  return (
    <main className="min-h-screen bg-black text-white p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-gray-400 hover:text-white">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-3xl font-bold">Monitoring</h1>
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-400">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded bg-gray-800 border-gray-600"
              />
              Auto-refresh (10s)
            </label>
            <button
              onClick={fetchData}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 rounded hover:bg-gray-700 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <button
              onClick={triggerSync}
              disabled={triggering}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 rounded hover:bg-blue-500 disabled:opacity-50 transition-colors"
            >
              {triggering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {triggering ? 'Running...' : 'Trigger Sync'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
            <div className="flex items-center gap-2 text-green-400">
              <CheckCircle className="w-5 h-5" />
              <span className="text-2xl font-bold">{successCount}</span>
            </div>
            <div className="text-sm text-gray-400 mt-1">Successful (recent)</div>
          </div>
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
            <div className="flex items-center gap-2 text-red-400">
              <XCircle className="w-5 h-5" />
              <span className="text-2xl font-bold">{errorCount}</span>
            </div>
            <div className="text-sm text-gray-400 mt-1">Errors (recent)</div>
          </div>
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
            <div className="flex items-center gap-2 text-blue-400">
              <Database className="w-5 h-5" />
              <span className="text-2xl font-bold">{tableStats.length}</span>
            </div>
            <div className="text-sm text-gray-400 mt-1">Active Tables</div>
          </div>
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
            <div className="flex items-center gap-2 text-purple-400">
              <TrendingUp className="w-5 h-5" />
              <span className="text-2xl font-bold">{totalRows.toLocaleString()}</span>
            </div>
            <div className="text-sm text-gray-400 mt-1">Rows (recent)</div>
          </div>
        </div>

        <div className="flex gap-2 mb-6">
          {(['recent', 'tables', 'charts'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg capitalize transition-colors ${
                activeTab === tab ? 'bg-blue-600' : 'bg-gray-800 hover:bg-gray-700'
              }`}
            >
              {tab === 'recent' ? 'Recent Syncs' : tab === 'tables' ? 'Table Status' : 'Charts'}
            </button>
          ))}
        </div>

        {activeTab === 'recent' && (
          <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-400">Table</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-400">Status</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-400">Rows</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-400">Duration</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-400">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {logs.map((log) => (
                  <tr key={log.LOG_ID} className="hover:bg-gray-800/50">
                    <td className="px-4 py-3 font-mono text-sm">{log.TABLE_ID}</td>
                    <td className="px-4 py-3">
                      {log.SYNC_STATUS === 'success' ? (
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircle className="w-4 h-4" /> Success
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-red-400 text-sm" title={log.SYNC_STATUS}>
                          <XCircle className="w-4 h-4" /> Error
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-sm">{(log.SYNC_RECORDS || 0).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-sm text-gray-400">{log.SYNC_DURATION_SEC}s</td>
                    <td className="px-4 py-3 text-right text-sm text-gray-400">
                      {new Date(log.LOGGED_AT).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                      No sync logs found. Trigger a sync to see data.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'tables' && (
          <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-800">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-400">Table</th>
                  <th className="px-4 py-3 text-center text-sm font-medium text-gray-400">Method</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-400">Last Status</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-400">Last Rows</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-gray-400">Last Sync</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {tableStats.map((t) => (
                  <tr key={t.TABLE_ID} className="hover:bg-gray-800/50">
                    <td className="px-4 py-3 font-mono text-sm">{t.TABLE_ID}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-xs font-medium uppercase ${getSyncMethodColor(t.SYNC_METHOD)}`}>
                        {t.SYNC_METHOD}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {t.LAST_SYNC_STATUS === 'success' ? (
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircle className="w-4 h-4" /> OK
                        </span>
                      ) : t.LAST_SYNC_STATUS ? (
                        <span className="flex items-center gap-1 text-red-400 text-sm">
                          <XCircle className="w-4 h-4" /> Error
                        </span>
                      ) : (
                        <span className="text-gray-500 text-sm">Never</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-sm">
                      {(t.LAST_SYNC_RECORDS || 0).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right text-sm text-gray-400">
                      {t.LAST_SYNC_AT ? new Date(t.LAST_SYNC_AT).toLocaleString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeTab === 'charts' && (
          <div className="space-y-6">
            <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
              <h3 className="text-lg font-semibold mb-4">Rows Synced (24h)</h3>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={chartData}>
                    <XAxis dataKey="hour" stroke="#6b7280" />
                    <YAxis stroke="#6b7280" />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                      labelStyle={{ color: '#9ca3af' }}
                    />
                    <Bar dataKey="rows" fill="#8b5cf6" name="Rows" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[300px] flex items-center justify-center text-gray-500">
                  No data available
                </div>
              )}
            </div>

            <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
              <h3 className="text-lg font-semibold mb-4">Sync Duration (avg seconds)</h3>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={chartData}>
                    <XAxis dataKey="hour" stroke="#6b7280" />
                    <YAxis stroke="#6b7280" />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                    />
                    <Line type="monotone" dataKey="duration" stroke="#3b82f6" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[200px] flex items-center justify-center text-gray-500">
                  No data available
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
