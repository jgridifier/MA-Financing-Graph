'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDeals, Deal } from '@/lib/api'
import { format } from 'date-fns'

export default function DealsPage() {
  const [query, setQuery] = useState('')
  const [sponsorFilter, setSponsorFilter] = useState<boolean | undefined>()
  const [marketTag, setMarketTag] = useState('')

  const { data: deals, isLoading } = useQuery({
    queryKey: ['deals', query, sponsorFilter, marketTag],
    queryFn: () => getDeals({
      query: query || undefined,
      is_sponsor_backed: sponsorFilter,
      market_tag: marketTag || undefined,
      limit: 100,
    }),
  })

  const formatCurrency = (value?: number) => {
    if (!value) return '-'
    if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
    if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`
    return `$${value.toLocaleString()}`
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">M&A Deals</h1>
      </div>

      <div className="bg-white p-4 rounded-lg shadow">
        <div className="flex flex-wrap gap-4">
          <input
            type="text"
            placeholder="Search deals..."
            className="flex-1 min-w-[200px] px-4 py-2 border border-gray-300 rounded-lg"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select
            className="px-4 py-2 border border-gray-300 rounded-lg"
            value={sponsorFilter === undefined ? '' : sponsorFilter ? 'true' : 'false'}
            onChange={(e) => {
              if (e.target.value === '') setSponsorFilter(undefined)
              else setSponsorFilter(e.target.value === 'true')
            }}
          >
            <option value="">All Deals</option>
            <option value="true">Sponsor-backed</option>
            <option value="false">Strategic</option>
          </select>
          <select
            className="px-4 py-2 border border-gray-300 rounded-lg"
            value={marketTag}
            onChange={(e) => setMarketTag(e.target.value)}
          >
            <option value="">All Market Tags</option>
            <option value="HY_Bond">HY Bond</option>
            <option value="IG_Bond">IG Bond</option>
            <option value="Term_Loan_B">Term Loan B</option>
            <option value="Bridge">Bridge</option>
          </select>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Target
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Acquirer
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Date
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Value
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
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
            ) : deals?.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-4 text-center text-gray-500">
                  No deals found
                </td>
              </tr>
            ) : (
              deals?.map((deal: Deal) => (
                <tr key={deal.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <a
                      href={`/deals/${deal.id}`}
                      className="text-blue-600 hover:text-blue-800 font-medium"
                    >
                      {deal.target_name_display || 'Unknown Target'}
                    </a>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-gray-900">
                    {deal.acquirer_name_display || 'Unknown'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-gray-500">
                    {deal.announcement_date
                      ? format(new Date(deal.announcement_date), 'MMM d, yyyy')
                      : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-gray-900">
                    {formatCurrency(deal.deal_value_usd)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      {deal.is_sponsor_backed && (
                        <span className="px-2 py-1 text-xs font-medium rounded bg-purple-100 text-purple-800">
                          Sponsor
                        </span>
                      )}
                      {deal.market_tag && (
                        <span className="px-2 py-1 text-xs font-medium rounded bg-blue-100 text-blue-800">
                          {deal.market_tag}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span
                      className={`px-2 py-1 text-xs font-medium rounded ${
                        deal.state === 'OPEN'
                          ? 'bg-green-100 text-green-800'
                          : deal.state === 'CANDIDATE'
                          ? 'bg-yellow-100 text-yellow-800'
                          : deal.state === 'CLOSED'
                          ? 'bg-gray-100 text-gray-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {deal.state}
                    </span>
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
