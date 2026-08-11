'use client'

import { ReactNode } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'

import { Badge } from '@/components/Badge'
import { DataProduct } from '@/lib/api-client'
import { useApiResource } from '@/lib/hooks/use-api-resource'

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-900">{value || '—'}</dd>
    </div>
  )
}

export default function ProductDetailPage() {
  const params = useParams<{ id: string }>()
  const { data, error, isLoading } = useApiResource<DataProduct>(`/api/core/data-products/${params.id}/`)

  return (
    <div>
      <Link href="/products" className="text-sm text-slate-500 hover:underline">
        &larr; Back to catalog
      </Link>

      {isLoading && <p className="mt-4 text-sm text-slate-500">Loading…</p>}
      {error && (
        <p className="mt-4 text-sm text-red-600">Could not load this data product ({error.status}).</p>
      )}

      {data && (
        <>
          <h1 className="mt-2 text-xl font-semibold text-slate-900">{data.title}</h1>
          <p className="mt-1 text-sm text-slate-600">{data.purpose || 'No purpose recorded.'}</p>

          <div className="mt-6 flex flex-wrap gap-2">
            <Badge value={data.sensitivity_classification} />
            <Badge value={data.transformation_status} />
            <Badge value={data.quality_status} />
          </div>

          <dl className="mt-8 grid grid-cols-2 gap-6 rounded-lg border border-slate-200 bg-white p-6 sm:grid-cols-3">
            <Field label="Data owner" value={data.data_owner} />
            <Field label="Source" value={data.source} />
            <Field label="Geographic coverage" value={data.geographic_coverage} />
            <Field
              label="Temporal coverage"
              value={
                data.temporal_coverage_start && data.temporal_coverage_end
                  ? `${data.temporal_coverage_start} – ${data.temporal_coverage_end}`
                  : ''
              }
            />
            <Field label="Schema version" value={data.schema_version} />
            <Field label="Indicator" value={data.indicator?.name} />
            <Field
              label="Refresh date"
              value={data.refresh_date ? new Date(data.refresh_date).toLocaleString() : ''}
            />
            <Field label="Last updated" value={new Date(data.updated_at).toLocaleString()} />
            <Field
              label="Permitted audience"
              value={data.permitted_audience.length > 0 ? data.permitted_audience.join(', ') : ''}
            />
          </dl>

          {(data.join_strategy || data.transformation_description) && (
            <div className="mt-6 space-y-4 rounded-lg border border-slate-200 bg-white p-6">
              <h2 className="text-sm font-semibold text-slate-900">Join &amp; transformation</h2>
              {data.join_strategy && (
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Join strategy</dt>
                  <dd className="mt-1 text-sm text-slate-700">{data.join_strategy}</dd>
                </div>
              )}
              {data.transformation_description && (
                <div>
                  <dt className="text-xs uppercase tracking-wide text-slate-500">Transformation</dt>
                  <dd className="mt-1 text-sm text-slate-700">{data.transformation_description}</dd>
                </div>
              )}
            </div>
          )}

          {data.sources.length > 0 && (
            <div className="mt-6 rounded-lg border border-slate-200 bg-white p-6">
              <h2 className="text-sm font-semibold text-slate-900">Provenance</h2>
              <ul className="mt-4 space-y-4">
                {data.sources.map((source, i) => (
                  <li key={source.id} className="border-l-2 border-slate-200 pl-4">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Source {i + 1}</p>
                    <p className="mt-1 text-sm font-medium text-slate-900">{source.name}</p>
                    {source.description && <p className="mt-1 text-sm text-slate-600">{source.description}</p>}
                    <p className="mt-1 text-xs text-slate-500">
                      {source.extraction_date && `Extracted ${source.extraction_date}`}
                      {source.extraction_date && source.reference_period && ' · '}
                      {source.reference_period && `Reference period: ${source.reference_period}`}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  )
}
