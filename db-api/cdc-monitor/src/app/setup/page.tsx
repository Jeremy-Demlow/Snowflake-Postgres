'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { ArrowLeft, Database, Table, Zap, RefreshCw, CheckCircle, AlertCircle, Settings2 } from 'lucide-react'

interface TableConfig {
  TABLE_ID: string
  SOURCE_TABLE: string
  TARGET_TABLE: string
  SYNC_METHOD: string
  SYNC_ENABLED: boolean
  WAL_SLOT_NAME: string | null
  CDC_COLUMN: string | null
  DATABASE_ID: string
  SOURCE_DB_NAME: string
  TARGET_SCHEMA: string
}

export default function SetupPage() {
  const [tables, setTables] = useState<TableConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'tables' | 'wal' | 'guide'>('tables')

  useEffect(() => {
    fetch('/api/tables')
      .then(res => res.json())
      .then(data => {
        setTables(data.tables)
        setLoading(false)
      })
  }, [])

  const databases = Array.from(new Set(tables.map(t => t.DATABASE_ID)))

  const getSyncMethodBadge = (method: string) => {
    const colors: Record<string, string> = {
      full: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
      cdc: 'bg-green-500/20 text-green-400 border-green-500/50',
      wal: 'bg-purple-500/20 text-purple-400 border-purple-500/50',
    }
    return colors[method?.toLowerCase()] || 'bg-gray-500/20 text-gray-400'
  }

  return (
    <main className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-4 mb-8">
          <Link href="/" className="text-gray-400 hover:text-white">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h1 className="text-3xl font-bold">Setup & Configuration</h1>
        </div>

        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab('tables')}
            className={`px-4 py-2 rounded-lg flex items-center gap-2 ${
              activeTab === 'tables' ? 'bg-blue-600' : 'bg-gray-800 hover:bg-gray-700'
            }`}
          >
            <Table className="w-4 h-4" /> Tables
          </button>
          <button
            onClick={() => setActiveTab('wal')}
            className={`px-4 py-2 rounded-lg flex items-center gap-2 ${
              activeTab === 'wal' ? 'bg-blue-600' : 'bg-gray-800 hover:bg-gray-700'
            }`}
          >
            <Zap className="w-4 h-4" /> WAL Slots
          </button>
          <button
            onClick={() => setActiveTab('guide')}
            className={`px-4 py-2 rounded-lg flex items-center gap-2 ${
              activeTab === 'guide' ? 'bg-blue-600' : 'bg-gray-800 hover:bg-gray-700'
            }`}
          >
            <Settings2 className="w-4 h-4" /> Setup Guide
          </button>
        </div>

        {activeTab === 'tables' && (
          <div className="space-y-6">
            {databases.map(dbId => (
              <div key={dbId} className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
                <div className="px-4 py-3 bg-gray-800 flex items-center gap-2">
                  <Database className="w-4 h-4 text-blue-400" />
                  <span className="font-semibold">{dbId}</span>
                  <span className="text-sm text-gray-400 ml-2">
                    ({tables.filter(t => t.DATABASE_ID === dbId).length} tables)
                  </span>
                </div>
                <table className="w-full">
                  <thead className="bg-gray-800/50">
                    <tr>
                      <th className="px-4 py-2 text-left text-sm font-medium text-gray-400">Source Table</th>
                      <th className="px-4 py-2 text-left text-sm font-medium text-gray-400">Target</th>
                      <th className="px-4 py-2 text-center text-sm font-medium text-gray-400">Method</th>
                      <th className="px-4 py-2 text-center text-sm font-medium text-gray-400">Enabled</th>
                      <th className="px-4 py-2 text-left text-sm font-medium text-gray-400">Config</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {tables.filter(t => t.DATABASE_ID === dbId).map(table => (
                      <tr key={table.TABLE_ID} className="hover:bg-gray-800/30">
                        <td className="px-4 py-2 font-mono text-sm">{table.SOURCE_TABLE}</td>
                        <td className="px-4 py-2 text-sm text-gray-400">{table.TARGET_SCHEMA}.{table.TARGET_TABLE}</td>
                        <td className="px-4 py-2 text-center">
                          <span className={`px-2 py-1 text-xs rounded border ${getSyncMethodBadge(table.SYNC_METHOD)}`}>
                            {table.SYNC_METHOD?.toUpperCase()}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-center">
                          {table.SYNC_ENABLED ? (
                            <CheckCircle className="w-4 h-4 text-green-400 mx-auto" />
                          ) : (
                            <AlertCircle className="w-4 h-4 text-gray-500 mx-auto" />
                          )}
                        </td>
                        <td className="px-4 py-2 text-xs text-gray-400">
                          {table.SYNC_METHOD === 'wal' && table.WAL_SLOT_NAME && (
                            <span>slot: {table.WAL_SLOT_NAME}</span>
                          )}
                          {table.SYNC_METHOD === 'cdc' && table.CDC_COLUMN && (
                            <span>watermark: {table.CDC_COLUMN}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'wal' && (
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <Zap className="w-5 h-5 text-purple-400" /> PostgreSQL WAL Replication Slots
            </h2>
            <div className="space-y-4">
              <div className="p-4 bg-gray-800 rounded-lg">
                <h3 className="font-semibold mb-2">Active Slots</h3>
                <div className="grid grid-cols-3 gap-4">
                  {['sf_cdc_customer_a', 'sf_cdc_customer_b', 'sf_cdc_customer_c'].map(slot => (
                    <div key={slot} className="p-3 bg-gray-900 rounded border border-gray-700">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                        <span className="font-mono text-sm">{slot}</span>
                      </div>
                      <div className="text-xs text-gray-400 mt-1">test_decoding</div>
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="p-4 bg-gray-800 rounded-lg">
                <h3 className="font-semibold mb-2">Create New WAL Slot</h3>
                <p className="text-sm text-gray-400 mb-3">
                  WAL slots capture INSERT, UPDATE, and DELETE operations at the database level.
                </p>
                <pre className="p-3 bg-gray-900 rounded text-sm font-mono overflow-x-auto">
{`-- Create a new replication slot
SELECT pg_create_logical_replication_slot(
  'slot_name',       -- Unique slot identifier
  'test_decoding'    -- Output plugin
);

-- Verify slot was created
SELECT * FROM pg_replication_slots;`}
                </pre>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'guide' && (
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-6 space-y-6">
            <h2 className="text-xl font-semibold">Setup Guide</h2>
            
            <div className="space-y-4">
              <div className="p-4 bg-gray-800 rounded-lg">
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <span className="w-6 h-6 bg-blue-600 rounded-full text-sm flex items-center justify-center">1</span>
                  Infrastructure Setup
                </h3>
                <pre className="p-3 bg-gray-900 rounded text-sm font-mono mt-2">
{`cd terraform
terraform init
terraform apply -auto-approve`}
                </pre>
              </div>

              <div className="p-4 bg-gray-800 rounded-lg">
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <span className="w-6 h-6 bg-blue-600 rounded-full text-sm flex items-center justify-center">2</span>
                  Deploy CDC Pipeline
                </h3>
                <pre className="p-3 bg-gray-900 rounded text-sm font-mono mt-2">
{`python deploy.py -c myconnection --pg-password "$PG_PASSWORD"

# This creates:
# - Stored procedures for sync
# - WAL replication slots  
# - TABLE_REGISTRY and DATABASE_REGISTRY
# - Task DAG for orchestration`}
                </pre>
              </div>

              <div className="p-4 bg-gray-800 rounded-lg">
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <span className="w-6 h-6 bg-blue-600 rounded-full text-sm flex items-center justify-center">3</span>
                  Configure Sync Methods
                </h3>
                <div className="mt-2 space-y-2 text-sm">
                  <div className="flex gap-4">
                    <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded">FULL</span>
                    <span className="text-gray-400">Truncate + reload. Best for dimension tables.</span>
                  </div>
                  <div className="flex gap-4">
                    <span className="px-2 py-1 bg-green-500/20 text-green-400 rounded">CDC</span>
                    <span className="text-gray-400">Watermark-based MERGE. Requires timestamp column.</span>
                  </div>
                  <div className="flex gap-4">
                    <span className="px-2 py-1 bg-purple-500/20 text-purple-400 rounded">WAL</span>
                    <span className="text-gray-400">Logical replication. Captures all DML operations.</span>
                  </div>
                </div>
              </div>

              <div className="p-4 bg-gray-800 rounded-lg">
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <span className="w-6 h-6 bg-blue-600 rounded-full text-sm flex items-center justify-center">4</span>
                  Run Sync
                </h3>
                <pre className="p-3 bg-gray-900 rounded text-sm font-mono mt-2">
{`-- Manual trigger
EXECUTE TASK DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG;

-- Or schedule (every 5 minutes)
ALTER TASK DBAPI_REPLICA_DB.UTILS.CDC_SYNC_DAG
SET SCHEDULE = '5 MINUTE';`}
                </pre>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
