'use client'

import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Search, TrendingUp, FileText, AlertCircle, Play } from 'lucide-react'
import { search, getDealStats, getFilingStats, getAlertStats, runPipeline, ingestFilings } from '@/lib/api'

export default function Home() {
  const [searchQuery, setSearchQuery] = useState('')
  const [cik, setCik] = useState('')

  const { data: dealStats } = useQuery({
    queryKey: ['dealStats'],
    queryFn: getDealStats,
  })

  const { data: filingStats } = useQuery({
    queryKey: ['filingStats'],
    queryFn: getFilingStats,
  })

  const { data: alertStats } = useQuery({
    queryKey: ['alertStats'],
    queryFn: getAlertStats,
  })

  const { data: searchResults } = useQuery({
    queryKey: ['search', searchQuery],
    queryFn: () => search(searchQuery),
    enabled: searchQuery.length > 2,
  })

  const pipelineMutation = useMutation({
    mutationFn: runPipeline,
  })

  const ingestMutation = useMutation({
    mutationFn: (cik: string) => ingestFilings({ cik, form_types: ['8-K', 'S-4', 'DEFM14A'] }),
  })

  return (
    <div className="space-y-6">
      <div className="text-center py-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">M&A Financing Graph</h1>
        <p className="text-lg text-gray-600 mb-8">
          SEC EDGAR M&A Deal and Debt Financing Analysis
        </p>

        <div className="max-w-xl mx-auto">
          <div className="relative">
            <Search className="absolute left-3 top-3 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search deals, companies, or banks..."
              className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          {searchResults && searchResults.results?.deals?.length > 0 && (
            <div className="mt-2 bg-white border rounded-lg shadow-lg">
              {searchResults.results.deals.map((deal: any) => (
                <a
                  key={deal.id}
                  href={`/deals/${deal.id}`}
                  className="block px-4 py-3 hover:bg-gray-50 border-b last:border-b-0"
                >
                  <div className="font-medium text-gray-900">{deal.title}</div>
                  {deal.subtitle && (
                    <div className="text-sm text-gray-500">{deal.subtitle}</div>
                  )}
                </a>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-lg shadow">
          <div className="flex items-center">
            <TrendingUp className="h-8 w-8 text-blue-500" />
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Total Deals</p>
              <p className="text-2xl font-semibold text-gray-900">
                {dealStats?.total_deals || 0}
              </p>
            </div>
          </div>
          <div className="mt-4 text-sm text-gray-600">
            Sponsor-backed: {dealStats?.sponsor_backed || 0}
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="flex items-center">
            <FileText className="h-8 w-8 text-green-500" />
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Filings Processed</p>
              <p className="text-2xl font-semibold text-gray-900">
                {filingStats?.processed || 0}
              </p>
            </div>
          </div>
          <div className="mt-4 text-sm text-gray-600">
            Total: {filingStats?.total_filings || 0}
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="flex items-center">
            <AlertCircle className="h-8 w-8 text-amber-500" />
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Pending Alerts</p>
              <p className="text-2xl font-semibold text-gray-900">
                {alertStats?.unresolved || 0}
              </p>
            </div>
          </div>
          <div className="mt-4 text-sm text-gray-600">
            Total alerts: {alertStats?.total_alerts || 0}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Ingest Company Filings</h2>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Enter CIK (e.g., 0001418091)"
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg"
              value={cik}
              onChange={(e) => setCik(e.target.value)}
            />
            <button
              onClick={() => cik && ingestMutation.mutate(cik)}
              disabled={!cik || ingestMutation.isPending}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {ingestMutation.isPending ? 'Ingesting...' : 'Ingest'}
            </button>
          </div>
          {ingestMutation.isSuccess && (
            <p className="mt-2 text-sm text-green-600">Ingestion started!</p>
          )}
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Run Processing Pipeline</h2>
          <p className="text-sm text-gray-600 mb-4">
            Cluster facts, reconcile financing, classify deals, and calculate fees.
          </p>
          <button
            onClick={() => pipelineMutation.mutate()}
            disabled={pipelineMutation.isPending}
            className="flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
          >
            <Play className="h-4 w-4 mr-2" />
            {pipelineMutation.isPending ? 'Running...' : 'Run Pipeline'}
          </button>
          {pipelineMutation.isSuccess && (
            <pre className="mt-2 text-xs text-gray-600 bg-gray-50 p-2 rounded overflow-auto max-h-40">
              {JSON.stringify(pipelineMutation.data, null, 2)}
            </pre>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <a
          href="/deals"
          className="block bg-white p-4 rounded-lg shadow hover:shadow-md transition"
        >
          <h3 className="font-semibold text-gray-900">Browse Deals</h3>
          <p className="text-sm text-gray-600">View all M&A deals with financing details</p>
        </a>
        <a
          href="/filings"
          className="block bg-white p-4 rounded-lg shadow hover:shadow-md transition"
        >
          <h3 className="font-semibold text-gray-900">View Filings</h3>
          <p className="text-sm text-gray-600">Browse SEC EDGAR filings and exhibits</p>
        </a>
        <a
          href="/alerts"
          className="block bg-white p-4 rounded-lg shadow hover:shadow-md transition"
        >
          <h3 className="font-semibold text-gray-900">Review Alerts</h3>
          <p className="text-sm text-gray-600">Handle items requiring manual review</p>
        </a>
      </div>
    </div>
  )
}
