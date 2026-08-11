'use client'

import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Badge } from '@/components/Badge'
import { ForbiddenNotice } from '@/components/ForbiddenNotice'
import { RoleGate } from '@/components/RoleGate'
import { DataProduct, FHIRValidationResult } from '@/lib/api-client'
import { useApiResource } from '@/lib/hooks/use-api-resource'

const QUALITY_STATUS_ORDER = ['unscreened', 'publishable', 'publishable_with_warnings', 'blocked']

export function ConformityView() {
  const { data: products } = useApiResource<DataProduct[]>('/api/core/data-products/')

  const qualityCounts = useMemo(() => {
    const counts: Record<string, number> = { unscreened: 0, publishable: 0, publishable_with_warnings: 0, blocked: 0 }
    products?.forEach((p) => {
      counts[p.quality_status] = (counts[p.quality_status] ?? 0) + 1
    })
    return QUALITY_STATUS_ORDER.map((status) => ({ status, count: counts[status] ?? 0 }))
  }, [products])

  return (
    <div className="space-y-8">
      <div>
        <h3 className="text-sm font-medium text-slate-700">Publication decision (FR6.6)</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={qualityCounts} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12 }} />
            <YAxis dataKey="status" type="category" tick={{ fontSize: 12 }} width={160} />
            <Tooltip />
            <Bar dataKey="count" fill="#0f172a" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h3 className="text-sm font-medium text-slate-700">Data quality assessment, per product</h3>
        <p className="mt-1 text-xs text-slate-500">
          Every check is labeled by method — deterministic (a hard fact), heuristic (a statistical judgement
          call, can have false positives), or a required human approval that is never evaluated by code.
        </p>
        <div className="mt-3 space-y-4">
          {products?.map((product) => <QualityChecksCard key={product.id} product={product} />)}
          {products?.length === 0 && <p className="text-sm text-slate-400">No data products yet.</p>}
        </div>
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

function QualityChecksCard({ product }: { product: DataProduct }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-4 border-b border-slate-100 px-4 py-3">
        <p className="text-sm font-medium text-slate-900">{product.title}</p>
        <Badge value={product.quality_status} />
      </div>
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Check</th>
            <th className="px-4 py-2">Method</th>
            <th className="px-4 py-2">Result</th>
            <th className="px-4 py-2">Detail</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {product.quality_checks.map((check) => (
            <tr key={check.id}>
              <td className="px-4 py-2 text-slate-900">{check.check_name}</td>
              <td className="px-4 py-2">
                <Badge value={check.method} />
              </td>
              <td className="px-4 py-2">
                <span className={check.passed ? 'text-emerald-700' : 'text-red-700'}>
                  {check.passed ? 'Pass' : 'Fail'}
                </span>
              </td>
              <td className="px-4 py-2 text-slate-600">{check.detail}</td>
            </tr>
          ))}
          {product.quality_checks.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-4 text-center text-slate-400">
                Not yet screened.
              </td>
            </tr>
          )}
        </tbody>
      </table>
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
