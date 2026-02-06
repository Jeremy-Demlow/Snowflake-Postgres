import Link from 'next/link'
import { Database, Activity, Settings, FileText } from 'lucide-react'

export default function Home() {
  return (
    <main className="min-h-screen p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-4xl font-bold mb-2">CDC Monitor</h1>
        <p className="text-gray-400 mb-8">PostgreSQL to Snowflake Change Data Capture Pipeline</p>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Link href="/setup" className="block p-6 bg-gray-900 rounded-lg border border-gray-800 hover:border-blue-500 transition-colors">
            <Settings className="w-8 h-8 mb-4 text-blue-400" />
            <h2 className="text-xl font-semibold mb-2">Setup</h2>
            <p className="text-gray-400 text-sm">Configure databases, tables, WAL slots, and sync methods</p>
          </Link>
          
          <Link href="/monitoring" className="block p-6 bg-gray-900 rounded-lg border border-gray-800 hover:border-green-500 transition-colors">
            <Activity className="w-8 h-8 mb-4 text-green-400" />
            <h2 className="text-xl font-semibold mb-2">Monitoring</h2>
            <p className="text-gray-400 text-sm">Real-time sync status, throughput metrics, and health checks</p>
          </Link>
          
          <Link href="/logs" className="block p-6 bg-gray-900 rounded-lg border border-gray-800 hover:border-purple-500 transition-colors">
            <FileText className="w-8 h-8 mb-4 text-purple-400" />
            <h2 className="text-xl font-semibold mb-2">Forensic Logs</h2>
            <p className="text-gray-400 text-sm">Complete sync history with filtering and error analysis</p>
          </Link>
        </div>

        <div className="mt-12 p-6 bg-gray-900 rounded-lg border border-gray-800">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Database className="w-5 h-5" /> Quick Stats
          </h3>
          <div className="grid grid-cols-4 gap-4 text-center">
            <div className="p-4 bg-gray-800 rounded">
              <div className="text-2xl font-bold text-blue-400">3</div>
              <div className="text-sm text-gray-400">Databases</div>
            </div>
            <div className="p-4 bg-gray-800 rounded">
              <div className="text-2xl font-bold text-green-400">42</div>
              <div className="text-sm text-gray-400">Tables</div>
            </div>
            <div className="p-4 bg-gray-800 rounded">
              <div className="text-2xl font-bold text-purple-400">3</div>
              <div className="text-sm text-gray-400">WAL Slots</div>
            </div>
            <div className="p-4 bg-gray-800 rounded">
              <div className="text-2xl font-bold text-yellow-400">~18M</div>
              <div className="text-sm text-gray-400">Rows Synced</div>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
