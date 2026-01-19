'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAlerts, resolveAlert, Alert } from '@/lib/api'
import { format } from 'date-fns'
import { AlertCircle, CheckCircle, ExternalLink, User } from 'lucide-react'

export default function AlertsPage() {
  const queryClient = useQueryClient()
  const [showResolved, setShowResolved] = useState(false)
  const [resolvingId, setResolvingId] = useState<number | null>(null)
  const [resolveNotes, setResolveNotes] = useState('')

  const { data: alerts, isLoading } = useQuery({
    queryKey: ['alerts', showResolved],
    queryFn: () => getAlerts({ is_resolved: showResolved ? undefined : false }),
  })

  const resolveMutation = useMutation({
    mutationFn: ({ id, notes }: { id: number; notes: string }) =>
      resolveAlert(id, { resolved_by: 'user', resolution_notes: notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
      setResolvingId(null)
      setResolveNotes('')
    },
  })

  const getAlertTypeColor = (type: string) => {
    switch (type) {
      case 'UNPARSED_MATERIAL_EXHIBIT':
        return 'bg-red-100 text-red-800'
      case 'FAILED_PRIVATE_TARGET_EXTRACTION':
        return 'bg-orange-100 text-orange-800'
      case 'LOW_CONFIDENCE_MATCH':
        return 'bg-yellow-100 text-yellow-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">Processing Alerts</h1>
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(e) => setShowResolved(e.target.checked)}
            className="mr-2"
          />
          Show resolved
        </label>
      </div>

      <div className="space-y-4">
        {isLoading ? (
          <div className="text-center py-8">Loading...</div>
        ) : alerts?.length === 0 ? (
          <div className="bg-white p-8 rounded-lg shadow text-center">
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
            <p className="text-gray-600">No pending alerts</p>
          </div>
        ) : (
          alerts?.map((alert: Alert) => (
            <div
              key={alert.id}
              className={`bg-white p-6 rounded-lg shadow ${
                alert.is_resolved ? 'opacity-60' : ''
              }`}
            >
              <div className="flex justify-between items-start">
                <div className="flex items-start space-x-4">
                  <AlertCircle
                    className={`h-6 w-6 ${
                      alert.is_resolved ? 'text-gray-400' : 'text-amber-500'
                    }`}
                  />
                  <div>
                    <h3 className="font-medium text-gray-900">{alert.title}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`px-2 py-0.5 text-xs font-medium rounded ${getAlertTypeColor(
                          alert.alert_type
                        )}`}
                      >
                        {alert.alert_type}
                      </span>
                      <span className="text-sm text-gray-500">
                        {format(new Date(alert.created_at), 'MMM d, yyyy h:mm a')}
                      </span>
                    </div>
                    {alert.description && (
                      <p className="text-sm text-gray-600 mt-2">{alert.description}</p>
                    )}

                    {alert.fields_needed && alert.fields_needed.length > 0 && (
                      <div className="mt-3">
                        <p className="text-sm font-medium text-gray-700">
                          Fields needed:
                        </p>
                        <ul className="list-disc list-inside text-sm text-gray-600">
                          {alert.fields_needed.map((field) => (
                            <li key={field}>{field}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {alert.exhibit_link && (
                      <a
                        href={alert.exhibit_link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center text-sm text-blue-600 hover:text-blue-800 mt-2"
                      >
                        <ExternalLink className="h-4 w-4 mr-1" />
                        View Exhibit
                      </a>
                    )}
                  </div>
                </div>

                {alert.is_resolved ? (
                  <div className="text-right text-sm">
                    <span className="flex items-center text-green-600">
                      <CheckCircle className="h-4 w-4 mr-1" />
                      Resolved
                    </span>
                    {alert.resolved_by && (
                      <div className="text-gray-500 flex items-center justify-end mt-1">
                        <User className="h-3 w-3 mr-1" />
                        {alert.resolved_by}
                      </div>
                    )}
                  </div>
                ) : resolvingId === alert.id ? (
                  <div className="space-y-2">
                    <textarea
                      placeholder="Resolution notes..."
                      className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                      rows={2}
                      value={resolveNotes}
                      onChange={(e) => setResolveNotes(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() =>
                          resolveMutation.mutate({
                            id: alert.id,
                            notes: resolveNotes,
                          })
                        }
                        disabled={resolveMutation.isPending}
                        className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => {
                          setResolvingId(null)
                          setResolveNotes('')
                        }}
                        className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-sm hover:bg-gray-300"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setResolvingId(alert.id)}
                    className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
                  >
                    Resolve
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
