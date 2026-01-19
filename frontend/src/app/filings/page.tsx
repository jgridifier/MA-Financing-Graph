'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getFilings, Filing } from '@/lib/api'
import { format } from 'date-fns'
import { ExternalLink, CheckCircle, XCircle } from 'lucide-react'

export default function FilingsPage() {
  const [cik, setCik] = useState('')
  const [formType, setFormType] = useState('')

  const { data: filings, isLoading } = useQuery({
    queryKey: ['filings', cik, formType],
    queryFn: () => getFilings({
      cik: cik || undefined,
      form_type: formType || undefined,
      limit: 100,
    }),
  })

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">SEC EDGAR Filings</h1>
      </div>

      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex flex-wrap gap-4">
          <input
            type="text"
            placeholder="Filter by CIK..."
            className="px-4 py-2 border border-gray-300 rounded-lg"
            value={cik}
            onChange={(e) => setCik(e.target.value)}
          />
          <select
            className="px-4 py-2 border border-gray-300 rounded-lg"
            value={formType}
            onChange={(e) => setFormType(e.target.value)}
          >
            <option value="">All Form Types</option>
            <option value="8-K">8-K</option>
            <option value="S-4">S-4</option>
            <option value="DEFM14A">DEFM14A</option>
            <option value="8-K/A">8-K/A</option>
          </select>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Company
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Form
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Accession
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Filed
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Link
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-6 py-4 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : filings?.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-4 text-center text-gray-500">
                  No filings found
                </td>
              </tr>
            ) : (
              filings?.map((filing: Filing) => (
                <tr key={filing.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="font-medium text-gray-900">
                      {filing.company_name || 'Unknown'}
                    </div>
                    <div className="text-sm text-gray-500">CIK: {filing.cik}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 py-1 text-sm font-medium rounded bg-blue-100 text-blue-800">
                      {filing.form_type}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 font-mono">
                    {filing.accession_number}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {format(new Date(filing.filing_date), 'MMM d, yyyy')}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {filing.processed ? (
                      <span className="flex items-center text-green-600">
                        <CheckCircle className="h-4 w-4 mr-1" />
                        Processed
                      </span>
                    ) : (
                      <span className="flex items-center text-gray-400">
                        <XCircle className="h-4 w-4 mr-1" />
                        Pending
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {filing.filing_url && (
                      <a
                        href={filing.filing_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:text-blue-800 flex items-center"
                      >
                        <ExternalLink className="h-4 w-4 mr-1" />
                        EDGAR
                      </a>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
