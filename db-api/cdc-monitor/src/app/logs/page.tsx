'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { ArrowLeft, Search, Filter, Download, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'

interface SyncLog {
  LOG_ID: number
  TABLE_ID: string
  SYNC_STATUS: string
  SYNC_RECORDS: number
  SYNC_DURATION_SEC: number
  NEW_WATERMARK: string | null
  CDC_ROWS: number | null
  LOGGED_AT: string
}

export default function LogsPage() {
  const [logs, setLogs] = useState<SyncLog[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'success' | 'error'>('all')
  const [search, setSearch] = useState('')
  const [limit, setLimit] = useState(100)
  const [selectedLog, setSelectedLog] = useState<SyncLog | null>(null)

  const fetchLogs = async () => {
    setLoading(true)
    const params = new URLSearchParams({
      limit: limit.toString(),
      status: filter,
      table: search,
    })
    const res = await fetch(`/api/sync-logs?${params}`)
    const data = await res.json()
    setLogs(data.logs)
    setLoading(false)
  }

  useEffect(() => {
    fetchLogs()
  }, [filter, limit])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    fetchLogs()
  }

  const exportCSV = () => {
    const headers = ['LOG_ID', 'TABLE_ID', 'SYNC_STATUS', 'SYNC_RECORDS', 'SYNC_DURATION_SEC', 'LOGGED_AT']
    const csv = [
      headers.join(','),
      ...logs.map(log => [
        log.LOG_ID,
        log.TABLE_ID,
        `"${log.SYNC_STATUS}"`,
        log.SYNC_RECORDS,
        log.SYNC_DURATION_SEC,
        log.LOGGED_AT
      ].join(','))
    ].join('\n')
    
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `sync-logs-${new Date().toISOString().slice(0,10)}.csv`
    a.click()
  }

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-gray-400 hover:text-white">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-3xl font-bold">Forensic Logs</h1>
          </div>
          <button
            onClick={exportCSV}
            className="flex items-center gap-2 px-4 py-2 bg-gray-800 rounded hover:bg-gray-700"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        </div>

        <div className="flex gap-4 mb-6">
          <form onSubmit={handleSearch} className="flex-1">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by table name..."
                className="w-full pl-10 pr-4 py-2 bg-gray-900 border border-gray-800 rounded focus:outline-none focus:border-blue-500"
              />
            </div>
          </form>
          
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-400" />
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as typeof filter)}
              className="px-3 py-2 bg-gray-900 border border-gray-800 rounded"
            >
              <option value="all">All Status</option>
              <option value="success">Success Only</option>
              <option value="error">Errors Only</option>
            </select>
            <select
              value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value))}
              className="px-3 py-2 bg-gray-900 border border-gray-800 rounded"
            >
              <option value="50">50 rows</option>
              <option value="100">100 rows</option>
              <option value="500">500 rows</option>
              <option value="1000">1000 rows</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
            <div className="max-h-[70vh] overflow-auto">
              <table className="w-full">
                <thead className="bg-gray-800 sticky top-0">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-400">ID</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-400">Table</th>
                    <th className="px-4 py-3 text-center text-sm font-medium text-gray-400">Status</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-gray-400">Rows</th>
                    <th className="px-4 py-3 text-right text-sm font-medium text-gray-400">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {logs.map((log) => (
                    <tr
                      key={log.LOG_ID}
                      onClick={() => setSelectedLog(log)}
                      className={`hover:bg-gray-800/50 cursor-pointer ${selectedLog?.LOG_ID === log.LOG_ID ? 'bg-gray-800' : ''}`}
                    >
                      <td className="px-4 py-2 text-sm text-gray-400">{log.LOG_ID}</td>
                      <td className="px-4 py-2 font-mono text-sm">{log.TABLE_ID}</td>
                      <td className="px-4 py-2 text-center">
                        {log.SYNC_STATUS === 'success' ? (
                          <CheckCircle className="w-4 h-4 text-green-400 mx-auto" />
                        ) : (
                          <XCircle className="w-4 h-4 text-red-400 mx-auto" />
                        )}
                      </td>
                      <td className="px-4 py-2 text-right text-sm">{(log.SYNC_RECORDS || 0).toLocaleString()}</td>
                      <td className="px-4 py-2 text-right text-sm text-gray-400">
                        {new Date(log.LOGGED_AT).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h3 className="text-lg font-semibold mb-4">Log Details</h3>
            {selectedLog ? (
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400">Table ID</label>
                  <p className="font-mono">{selectedLog.TABLE_ID}</p>
                </div>
                <div>
                  <label className="text-sm text-gray-400">Status</label>
                  <p className={selectedLog.SYNC_STATUS === 'success' ? 'text-green-400' : 'text-red-400'}>
                    {selectedLog.SYNC_STATUS}
                  </p>
                </div>
                <div>
                  <label className="text-sm text-gray-400">Rows Synced</label>
                  <p>{(selectedLog.SYNC_RECORDS || 0).toLocaleString()}</p>
                </div>
                <div>
                  <label className="text-sm text-gray-400">Duration</label>
                  <p>{selectedLog.SYNC_DURATION_SEC} seconds</p>
                </div>
                {selectedLog.NEW_WATERMARK && (
                  <div>
                    <label className="text-sm text-gray-400">Watermark</label>
                    <p className="font-mono text-sm">{selectedLog.NEW_WATERMARK}</p>
                  </div>
                )}
                <div>
                  <label className="text-sm text-gray-400">Logged At</label>
                  <p>{new Date(selectedLog.LOGGED_AT).toLocaleString()}</p>
                </div>
                {selectedLog.SYNC_STATUS.startsWith('error') && (
                  <div className="p-3 bg-red-900/20 border border-red-800 rounded">
                    <div className="flex items-center gap-2 text-red-400 mb-2">
                      <AlertTriangle className="w-4 h-4" />
                      <span className="font-semibold">Error Details</span>
                    </div>
                    <p className="text-sm text-red-300 font-mono break-all">
                      {selectedLog.SYNC_STATUS.replace('error: ', '')}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-gray-400 text-sm">Select a log entry to view details</p>
            )}
          </div>
        </div>
      </div>
    </main>
  )
}
