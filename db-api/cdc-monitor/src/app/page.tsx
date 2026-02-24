'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Database, Activity, Settings, FileText, RefreshCw, AlertCircle, CheckCircle, DollarSign } from 'lucide-react'

interface HealthData {
  status: string
  snowflake: { connected: boolean; error?: string }
  stats?: Record<string, number>
  error?: string
}

interface CostData {
  summary: {
    totalCredits: number
    estCostUsd: number
    syncCount30d: number
    creditsPerSync: number
  }
  projections: {
    currentScale: { estMonthlyCost: number }
    atScale: { estMonthlyCost: number }
  }
}

export default function Home() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [costs, setCosts] = useState<CostData | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchHealth = async () => {
    setLoading(true)
    try {
      const [healthRes, costsRes] = await Promise.all([
        fetch('/api/health'),
        fetch('/api/costs')
      ])
      const healthData = await healthRes.json()
      const costsData = await costsRes.json()
      setHealth(healthData)
      setCosts(costsData)
    } catch (err) {
      setHealth({ status: 'error', snowflake: { connected: false, error: 'Failed to connect' } })
    }
    setLoading(false)
  }

  useEffect(() => {
    fetchHealth()
    const interval = setInterval(fetchHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  const rawStats = health?.stats || {}
  const stats = {
    databases: rawStats.databases ?? rawStats.DATABASES ?? 0,
    tables: rawStats.tables ?? rawStats.TABLES ?? 0,
    synced: rawStats.synced ?? rawStats.SYNCED ?? 0,
    total_rows: rawStats.total_rows ?? rawStats.TOTAL_ROWS ?? 0,
  }

  const formatRows = (n: number) => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
    if (n >= 1000) return `${(n / 1000).toFixed(0)}K`
    return n.toLocaleString()
  }

  return (
    <main className="min-h-screen bg-black text-white">
      <div className="max-w-6xl mx-auto p-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold mb-2">CDC Monitor</h1>
            <p className="text-gray-400">PostgreSQL to Snowflake Change Data Capture Pipeline</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              {health?.snowflake?.connected ? (
                <CheckCircle className="w-5 h-5 text-green-400" />
              ) : (
                <AlertCircle className="w-5 h-5 text-red-400" />
              )}
              <span className="text-sm text-gray-400">
                {health?.snowflake?.connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            <button
              onClick={fetchHealth}
              className="p-2 hover:bg-gray-800 rounded transition-colors"
              title="Refresh"
            >
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <Link href="/setup" className="block p-6 bg-gray-900 rounded-lg border border-gray-800 hover:border-blue-500 transition-colors group">
            <Settings className="w-8 h-8 mb-4 text-blue-400 group-hover:scale-110 transition-transform" />
            <h2 className="text-xl font-semibold mb-2">Setup</h2>
            <p className="text-gray-400 text-sm">Configure databases, tables, and sync methods</p>
          </Link>
          
          <Link href="/monitoring" className="block p-6 bg-gray-900 rounded-lg border border-gray-800 hover:border-green-500 transition-colors group">
            <Activity className="w-8 h-8 mb-4 text-green-400 group-hover:scale-110 transition-transform" />
            <h2 className="text-xl font-semibold mb-2">Monitoring</h2>
            <p className="text-gray-400 text-sm">Real-time sync status and health checks</p>
          </Link>
          
          <Link href="/logs" className="block p-6 bg-gray-900 rounded-lg border border-gray-800 hover:border-purple-500 transition-colors group">
            <FileText className="w-8 h-8 mb-4 text-purple-400 group-hover:scale-110 transition-transform" />
            <h2 className="text-xl font-semibold mb-2">Forensic Logs</h2>
            <p className="text-gray-400 text-sm">Complete sync history with filtering</p>
          </Link>
          
          <Link href="/costs" className="block p-6 bg-gray-900 rounded-lg border border-gray-800 hover:border-yellow-500 transition-colors group">
            <DollarSign className="w-8 h-8 mb-4 text-yellow-400 group-hover:scale-110 transition-transform" />
            <h2 className="text-xl font-semibold mb-2">Cost Tracking</h2>
            <p className="text-gray-400 text-sm">Pipeline costs and projections</p>
          </Link>
        </div>

        {costs && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
              <div className="text-sm text-gray-400">30-Day Credits</div>
              <div className="text-2xl font-bold text-yellow-400">{costs.summary.totalCredits}</div>
            </div>
            <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
              <div className="text-sm text-gray-400">30-Day Cost</div>
              <div className="text-2xl font-bold text-green-400">${costs.summary.estCostUsd}</div>
            </div>
            <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
              <div className="text-sm text-gray-400">Credits/Sync</div>
              <div className="text-2xl font-bold text-blue-400">{costs.summary.creditsPerSync.toFixed(4)}</div>
            </div>
            <div className="p-4 bg-gray-900 rounded-lg border border-gray-800">
              <div className="text-sm text-gray-400">Est. Monthly (2K tables)</div>
              <div className="text-2xl font-bold text-purple-400">${costs.projections.atScale.estMonthlyCost.toLocaleString()}</div>
            </div>
          </div>
        )}

        <div className="p-6 bg-gray-900 rounded-lg border border-gray-800">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Database className="w-5 h-5" /> Pipeline Status
          </h3>
          {loading && !health ? (
            <div className="text-center py-8 text-gray-400">
              <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-2" />
              Loading...
            </div>
          ) : health?.snowflake?.connected ? (
            <div className="grid grid-cols-4 gap-4">
              <div className="p-4 bg-gray-800 rounded text-center">
                <div className="text-3xl font-bold text-blue-400">{stats.databases}</div>
                <div className="text-sm text-gray-400 mt-1">Databases</div>
              </div>
              <div className="p-4 bg-gray-800 rounded text-center">
                <div className="text-3xl font-bold text-green-400">{stats.tables}</div>
                <div className="text-sm text-gray-400 mt-1">Tables</div>
              </div>
              <div className="p-4 bg-gray-800 rounded text-center">
                <div className="text-3xl font-bold text-purple-400">{stats.synced}</div>
                <div className="text-sm text-gray-400 mt-1">Synced OK</div>
              </div>
              <div className="p-4 bg-gray-800 rounded text-center">
                <div className="text-3xl font-bold text-yellow-400">{formatRows(stats.total_rows)}</div>
                <div className="text-sm text-gray-400 mt-1">Rows Synced</div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
              <p className="text-red-400 mb-2">Failed to connect to Snowflake</p>
              <p className="text-gray-500 text-sm">{health?.snowflake?.error || 'Check configuration'}</p>
            </div>
          )}
        </div>

        {health?.snowflake?.connected && (
          <div className="mt-6 p-4 bg-gray-900 rounded-lg border border-gray-800">
            <h4 className="text-sm font-medium text-gray-400 mb-2">Quick Actions</h4>
            <div className="flex gap-4">
              <Link href="/monitoring" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm transition-colors">
                View Live Syncs
              </Link>
              <Link href="/logs" className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm transition-colors">
                Check Logs
              </Link>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
