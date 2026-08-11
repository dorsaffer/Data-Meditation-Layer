'use client'

import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { ForbiddenNotice } from '@/components/ForbiddenNotice'
import { Observation } from '@/lib/api-client'
import { useApiResource } from '@/lib/hooks/use-api-resource'

export function DistrictComparisonChart() {
  const { data, error, isLoading } = useApiResource<Observation[]>('/api/core/observations/')
  const [indicatorUid, setIndicatorUid] = useState('')
  const [period, setPeriod] = useState('')

  const { indicators, periods, rows } = useMemo(() => {
    if (!data) return { indicators: [] as [string, string][], periods: [] as string[], rows: [] as { district: string; value: number }[] }

    const indicatorMap = new Map<string, string>()
    const periodSet = new Set<string>()
    data.forEach((obs) => {
      indicatorMap.set(obs.indicator.dhis2_dx_uid, obs.indicator.name)
      periodSet.add(obs.period)
    })
    const indicators = Array.from(indicatorMap.entries())
    const periods = Array.from(periodSet).sort()
    const activeIndicator = indicatorUid || indicators[0]?.[0] || ''
    const activePeriod = period || periods[periods.length - 1] || ''

    const rows = data
      .filter((obs) => obs.indicator.dhis2_dx_uid === activeIndicator && obs.period === activePeriod)
      .map((obs) => ({ district: obs.district.name, value: obs.value }))

    return { indicators, periods, rows }
  }, [data, indicatorUid, period])

  if (error?.status === 403) return <ForbiddenNotice roles={['analyst', 'auditor']} />
  if (error) return <p className="text-sm text-red-600">Could not load observations.</p>
  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>
  if (!data || data.length === 0) return <p className="text-sm text-slate-400">No observations yet.</p>

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-3 text-sm">
        <select
          className="rounded border border-slate-300 px-2 py-1"
          value={indicatorUid || indicators[0]?.[0] || ''}
          onChange={(e) => setIndicatorUid(e.target.value)}
        >
          {indicators.map(([uid, name]) => (
            <option key={uid} value={uid}>
              {name}
            </option>
          ))}
        </select>
        <select
          className="rounded border border-slate-300 px-2 py-1"
          value={period || periods[periods.length - 1] || ''}
          onChange={(e) => setPeriod(e.target.value)}
        >
          {periods.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="district" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey="value" fill="#0f172a" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
