'use client'

import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Badge } from '@/components/Badge'
import { ForbiddenNotice } from '@/components/ForbiddenNotice'
import { RoleGate } from '@/components/RoleGate'
import { DataProduct, FHIRValidationResult } from '@/lib/api-client'
import { useApiResource } from '@/lib/hooks/use-api-resource'

export function ConformityView() {
  const { data: products } = useApiResource<DataProduct[]>('/api/core/data-products/')

  const qualityCounts = useMemo(() => {
    const counts: Record<string, number> = { passed: 0, flagged: 0, unscreened: 0 }
    products?.forEach((p) => {
      counts[p.quality_status] = (counts[p.quality_status] ?? 0) + 1
    })
    return Object.entries(counts).map(([status, count]) => ({ status, count }))
  }, [products])

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-sm font-medium text-slate-700">Data product quality status</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={qualityCounts} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
            <YAxis dataKey="status" type="category" tick={{ fontSize: 12 }} width={90} />
            <Tooltip />
            <Bar dataKey="count" fill="#0f172a" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h3 className="text-sm font-medium text-slate-700">FHIR conformity checks</h3>
        <div className="mt-3">
          <RoleGate allow={['analyst', 'auditor']}>
            <FhirValidationTable />
          </RoleGate>
        </div>
      </div>
    </div>
  )
}

function FhirValidationTable() {
  const { data, error, isLoading } = useApiResource<FHIRValidationResult[]>('/api/core/fhir-validation-results/')

  if (error?.status === 403) return <ForbiddenNotice roles={['analyst', 'auditor']} />
  if (error) return <p className="text-sm text-red-600">Could not load FHIR conformity results.</p>
  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>

  const passCount = data?.filter((r) => r.is_valid).length ?? 0
  const failCount = (data?.length ?? 0) - passCount

  return (
    <div>
      <p className="text-xs text-slate-500">
        {passCount} passed · {failCount} failed, of {data?.length ?? 0} validated resources.
      </p>
      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Resource</th>
              <th className="px-4 py-2">Reference</th>
              <th className="px-4 py-2">Result</th>
              <th className="px-4 py-2">Validated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data?.map((result) => (
              <tr key={result.id}>
                <td className="px-4 py-2">{result.resource_type}</td>
                <td className="px-4 py-2 text-slate-600">{result.resource_reference}</td>
                <td className="px-4 py-2">
                  <Badge value={result.is_valid ? 'passed' : 'flagged'} />
                </td>
                <td className="px-4 py-2 text-slate-500">{new Date(result.validated_at).toLocaleString()}</td>
              </tr>
            ))}
            {data?.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                  No FHIR validation results yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
