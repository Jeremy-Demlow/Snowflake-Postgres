'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { ArrowLeft, RefreshCw, Play, CheckCircle, XCircle, Clock } from 'lucide-react'

interface SyncLog {
  LOG_ID: number
  TABLE_ID: string
  SYNC_STATUS: string
  SYNC_RECORDS: number
  SYNC_DURATION_SEC: number
  LOGGED_AT: string
}

export default function MonitoringPage() {
  const [logs, setLogs] = useState<SyncLog[]>([])
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchLogs = async () => {
    const res = await fetch('/api/sync-logs?limit=50')
    const data = await res.json()
    setLogs(data.logs)
    setLoading(false)
  }

  const triggerSync = async () => {
    setTriggering(true)
    await fetch('/api/trigger-sync', { method: 'POST' })
    setTimeout(() => {
      setTriggering(false)
      fetchLogs()
    }, 2000)
  }

  useEffect(() => {
    fetchLogs()
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 5000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh])

  const successCount = logs.filter(l => l.SYNC_STATUS === 'success').length
  const errorCount = logs.filter(l => l.SYNC_STATUS.startsWith('error')).length
  const totalRows = logs.reduce((acc, l) => acc + (l.SYNC_RECORDS || 0), 0)

  return (
    <main className="min-h-screen p-8">
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
                className="rounded"
              />
              Auto-refresh
            </label>
            <button
              onClick={fetchLogs}
              className="flex items-center gap-2 px-4 py-2 bg-gray-800 rounded hover:bg-gray-700"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <button
              onClick={triggerSync}
              disabled={triggering}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 rounded hover:bg-blue-500 disabled:opacity-50"
            >
              <Play className="w-4 h-4" />
              {triggering ? 'Triggering...' : 'Trigger Sync'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
            <div className="flex items-center gap-2 text-green-400">
              <CheckCircle className="w-5 h-5" />
              <span className="text-2xl font-bold">{successCount}</span>
            </div>
            <div className="text-sm text-gray-400 mt-1">Successful</div>
          </div>
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
            <div className="flex items-center gap-2 text-red-400">
              <XCircle className="w-5 h-5" />
              <span className="text-2xl font-bold">{errorCount}</span>
            </div>
            <div className="text-sm text-gray-400 mt-1">Errors</div>
          </div>
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
            <div className="flex items-center gap-2 text-blue-400">
              <Clock className="w-5 h-5" />
              <span className="text-2xl font-bold">{logs.length}</span>
            </div>
            <div className="text-sm text-gray-400 mt-1">Recent Syncs</div>
          </div>
          <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
            <div className="text-2xl font-bold text-purple-400">{totalRows.toLocaleString()}</div>
            <div className="text-sm text-gray-400 mt-1">Rows Synced</div>
          </div>
        </div>

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
            </tbody>
          </table>
        </div>
      </div>
    </main>
  )
}
