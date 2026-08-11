'use client'

import { ForbiddenNotice } from '@/components/ForbiddenNotice'
import { ServiceCoverageResponse } from '@/lib/api-client'
import { useApiResource } from '@/lib/hooks/use-api-resource'

export function ServiceCoverageView() {
  const { data, error, isLoading } = useApiResource<ServiceCoverageResponse>('/api/core/service-coverage/')

  if (error?.status === 403) return <ForbiddenNotice roles={['analyst', 'auditor']} />
  if (error) return <p className="text-sm text-red-600">Could not load service coverage.</p>
  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>
  if (!data || !data.indicator) return <p className="text-sm text-slate-400">No comparable data yet.</p>

  return (
    <div>
      <p className="text-xs text-slate-500">
        {data.indicator} · period {data.period} · population reference year {data.reference_year}
      </p>

      <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">{data.caveat}</div>

      <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">District</th>
              <th className="px-4 py-2">Population</th>
              <th className="px-4 py-2">Service activity</th>
              <th className="px-4 py-2">Ratio</th>
              <th className="px-4 py-2">Signal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.rows.map((row) => (
              <tr key={row.district_id} className={row.potentially_underserved ? 'bg-amber-50' : undefined}>
                <td className="px-4 py-2 font-medium text-slate-900">{row.district}</td>
                <td className="px-4 py-2 text-slate-600">
                  {row.population !== null ? row.population.toLocaleString() : '—'}
                </td>
                <td className="px-4 py-2 text-slate-600">
                  {row.service_activity !== null ? row.service_activity.toLocaleString() : '—'}
                </td>
                <td className="px-4 py-2 text-slate-600">
                  {row.ratio_percent !== null ? `${row.ratio_percent}%` : '—'}
                </td>
                <td className="px-4 py-2">
                  {row.excluded ? (
                    <span className="text-xs text-slate-400">excluded — {row.excluded_reason}</span>
                  ) : row.potentially_underserved ? (
                    <span className="inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
                      potentially underserved
                    </span>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
