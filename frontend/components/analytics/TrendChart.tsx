'use client'

import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { ForbiddenNotice } from '@/components/ForbiddenNotice'
import { Observation } from '@/lib/api-client'
import { useApiResource } from '@/lib/hooks/use-api-resource'

const ALL_DISTRICTS = '__all__'

export function TrendChart() {
  const { data, error, isLoading } = useApiResource<Observation[]>('/api/core/observations/')
  const [indicatorUid, setIndicatorUid] = useState('')
  const [districtUid, setDistrictUid] = useState(ALL_DISTRICTS)

  const { indicators, districts, rows } = useMemo(() => {
    if (!data) {
      return { indicators: [] as [string, string][], districts: [] as [string, string][], rows: [] as { period: string; value: number }[] }
    }

    const indicatorMap = new Map<string, string>()
    const districtMap = new Map<string, string>()
    data.forEach((obs) => {
      indicatorMap.set(obs.indicator.dhis2_dx_uid, obs.indicator.name)
      districtMap.set(obs.district.dhis2_org_unit_uid, obs.district.name)
    })
    const indicators = Array.from(indicatorMap.entries())
    const districts = Array.from(districtMap.entries())
    const activeIndicator = indicatorUid || indicators[0]?.[0] || ''

    const filtered = data.filter(
      (obs) =>
        obs.indicator.dhis2_dx_uid === activeIndicator &&
        (districtUid === ALL_DISTRICTS || obs.district.dhis2_org_unit_uid === districtUid),
    )

    const byPeriod = new Map<string, { total: number; count: number }>()
    filtered.forEach((obs) => {
      const entry = byPeriod.get(obs.period) ?? { total: 0, count: 0 }
      entry.total += obs.value
      entry.count += 1
      byPeriod.set(obs.period, entry)
    })
    const rows = Array.from(byPeriod.entries())
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(([p, { total, count }]) => ({ period: p, value: total / count }))

    return { indicators, districts, rows }
  }, [data, indicatorUid, districtUid])

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
          value={districtUid}
          onChange={(e) => setDistrictUid(e.target.value)}
        >
          <option value={ALL_DISTRICTS}>All districts (average)</option>
          {districts.map(([uid, name]) => (
            <option key={uid} value={uid}>
              {name}
            </option>
          ))}
        </select>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="period" tick={{ fontSize: 12 }} />
          <YAxis tick={{ fontSize: 12 }} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#0f172a" strokeWidth={2} dot={{ r: 3 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
