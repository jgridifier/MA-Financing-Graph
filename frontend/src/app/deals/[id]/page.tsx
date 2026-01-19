'use client'

import { useParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { getDeal, getDealFinancing, getDealAdvisors, getDealFacts } from '@/lib/api'
import { format } from 'date-fns'
import { ExternalLink, DollarSign, Building, Calendar, FileText } from 'lucide-react'

export default function DealDetailPage() {
  const params = useParams()
  const dealId = parseInt(params.id as string)

  const { data: deal, isLoading: dealLoading } = useQuery({
    queryKey: ['deal', dealId],
    queryFn: () => getDeal(dealId),
    enabled: !isNaN(dealId),
  })

  const { data: financing } = useQuery({
    queryKey: ['deal-financing', dealId],
    queryFn: () => getDealFinancing(dealId),
    enabled: !isNaN(dealId),
  })

  const { data: advisors } = useQuery({
    queryKey: ['deal-advisors', dealId],
    queryFn: () => getDealAdvisors(dealId),
    enabled: !isNaN(dealId),
  })

  const { data: facts } = useQuery({
    queryKey: ['deal-facts', dealId],
    queryFn: () => getDealFacts(dealId),
    enabled: !isNaN(dealId),
  })

  const formatCurrency = (value?: number) => {
    if (!value) return '-'
    if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`
    if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
    return `$${value.toLocaleString()}`
  }

  if (dealLoading) {
    return <div className="text-center py-8">Loading...</div>
  }

  if (!deal) {
    return <div className="text-center py-8">Deal not found</div>
  }

  return (
    <div className="space-y-6">
      <div className="bg-white p-6 rounded-lg shadow">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {deal.acquirer_name_display || 'Unknown'} / {deal.target_name_display || 'Unknown'}
            </h1>
            <div className="flex items-center gap-4 mt-2">
              {deal.is_sponsor_backed && (
                <span className="px-3 py-1 text-sm font-medium rounded bg-purple-100 text-purple-800">
                  Sponsor-backed
                </span>
              )}
              {deal.market_tag && (
                <span className="px-3 py-1 text-sm font-medium rounded bg-blue-100 text-blue-800">
                  {deal.market_tag}
                </span>
              )}
              <span
                className={`px-3 py-1 text-sm font-medium rounded ${
                  deal.state === 'OPEN'
                    ? 'bg-green-100 text-green-800'
                    : deal.state === 'CANDIDATE'
                    ? 'bg-yellow-100 text-yellow-800'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                {deal.state}
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mt-6">
          <div>
            <div className="flex items-center text-gray-500 text-sm">
              <DollarSign className="h-4 w-4 mr-1" />
              Deal Value
            </div>
            <div className="text-lg font-semibold">
              {formatCurrency(deal.deal_value_usd)}
            </div>
          </div>
          <div>
            <div className="flex items-center text-gray-500 text-sm">
              <Calendar className="h-4 w-4 mr-1" />
              Announcement
            </div>
            <div className="text-lg font-semibold">
              {deal.announcement_date
                ? format(new Date(deal.announcement_date), 'MMM d, yyyy')
                : '-'}
            </div>
          </div>
          <div>
            <div className="flex items-center text-gray-500 text-sm">
              <Building className="h-4 w-4 mr-1" />
              Sponsor
            </div>
            <div className="text-lg font-semibold">
              {deal.sponsor_name_display || '-'}
            </div>
          </div>
          <div>
            <div className="flex items-center text-gray-500 text-sm">
              <FileText className="h-4 w-4 mr-1" />
              Agreement
            </div>
            <div className="text-lg font-semibold">
              {deal.agreement_date
                ? format(new Date(deal.agreement_date), 'MMM d, yyyy')
                : '-'}
            </div>
          </div>
        </div>
      </div>

      {/* Financing Events */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h2 className="text-lg font-semibold mb-4">Financing Events</h2>
        {!financing || financing.length === 0 ? (
          <p className="text-gray-500">No financing events found</p>
        ) : (
          <div className="space-y-4">
            {financing.map((event) => (
              <div key={event.id} className="border rounded-lg p-4">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-medium">
                      {event.instrument_type || event.instrument_family}
                    </div>
                    <div className="text-sm text-gray-500">
                      {event.market_tag} • {event.purpose || 'Acquisition financing'}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-lg">
                      {formatCurrency(event.amount_usd)}
                    </div>
                    {event.estimated_fee_usd && (
                      <div className="text-sm text-gray-500">
                        Est. fee: {formatCurrency(event.estimated_fee_usd)}
                      </div>
                    )}
                  </div>
                </div>

                {event.participants && event.participants.length > 0 && (
                  <div className="mt-4">
                    <div className="text-sm font-medium text-gray-700 mb-2">
                      Participants
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                      {event.participants.map((p) => (
                        <div
                          key={p.id}
                          className="bg-gray-50 rounded p-2 text-sm"
                        >
                          <div className="font-medium">{p.bank_name_raw}</div>
                          <div className="text-gray-500">{p.role}</div>
                          {p.estimated_fee_usd && (
                            <div className="text-green-600">
                              {formatCurrency(p.estimated_fee_usd)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {event.reconciliation_explanation && (
                  <div className="mt-3 text-sm text-gray-500">
                    <span className="font-medium">Match: </span>
                    {event.reconciliation_explanation}
                    {event.reconciliation_confidence && (
                      <span className="ml-2">
                        ({(event.reconciliation_confidence * 100).toFixed(0)}% confidence)
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Financial Advisors */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h2 className="text-lg font-semibold mb-4">Financial Advisors</h2>
        {!advisors || advisors.length === 0 ? (
          <p className="text-gray-500">No advisors found</p>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {advisors.map((advisor, idx) => (
              <div key={idx} className="border rounded-lg p-4">
                <div className="font-medium">{advisor.bank_name_raw}</div>
                <div className="text-sm text-gray-500">
                  {advisor.role} • {advisor.client_side}
                </div>
                {advisor.evidence_snippet && (
                  <div className="mt-2 text-xs text-gray-400 truncate">
                    {advisor.evidence_snippet}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Fee Summary */}
      {(deal.advisory_fee_estimated || deal.underwriting_fee_estimated) && (
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-lg font-semibold mb-4">Estimated Fees</h2>
          <div className="grid grid-cols-2 gap-6">
            <div>
              <div className="text-sm text-gray-500">Advisory Fees</div>
              <div className="text-2xl font-semibold text-green-600">
                {formatCurrency(deal.advisory_fee_estimated)}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Underwriting Fees</div>
              <div className="text-2xl font-semibold text-blue-600">
                {formatCurrency(deal.underwriting_fee_estimated)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Evidence / Facts */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h2 className="text-lg font-semibold mb-4">Evidence Trail</h2>
        {!facts || facts.length === 0 ? (
          <p className="text-gray-500">No facts extracted</p>
        ) : (
          <div className="space-y-3 max-h-96 overflow-auto">
            {facts.map((fact: any) => (
              <div key={fact.id} className="border-l-4 border-gray-300 pl-4 py-2">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-100">
                    {fact.fact_type}
                  </span>
                  <span className="text-sm text-gray-500">
                    {fact.source_section}
                  </span>
                  {fact.confidence && (
                    <span className="text-xs text-gray-400">
                      {(fact.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div className="mt-1 text-sm text-gray-700 font-mono bg-gray-50 p-2 rounded">
                  {fact.evidence_snippet?.slice(0, 200)}...
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
