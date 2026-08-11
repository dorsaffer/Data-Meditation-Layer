'use client'

import { ReactNode } from 'react'

import { Badge } from '@/components/Badge'
import { ForbiddenNotice } from '@/components/ForbiddenNotice'
import { RoleGate } from '@/components/RoleGate'
import { DataProduct, PopulationDataQualityIssue, RawDHIS2Record, TerminologyMapping } from '@/lib/api-client'
import { useApiResource } from '@/lib/hooks/use-api-resource'

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 text-sm text-slate-500">{description}</p>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export default function GovernancePage() {
  const { data: products, error, isLoading } = useApiResource<DataProduct[]>('/api/core/data-products/')

  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-900">Governance</h1>
      <p className="mt-1 text-sm text-slate-500">
        Privacy flags, pipeline/quality status, and audit information, scoped to your role.
      </p>

      <div className="mt-6 space-y-6">
        <Section
          title="Privacy flags"
          description="Sensitivity classification and permitted audience per data product."
        >
          {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {error && <p className="text-sm text-red-600">Could not load data products ({error.status}).</p>}
          {products && (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-2">Data product</th>
                    <th className="px-4 py-2">Sensitivity</th>
                    <th className="px-4 py-2">Permitted audience</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {products.map((p) => (
                    <tr key={p.id}>
                      <td className="px-4 py-2 font-medium text-slate-900">{p.title}</td>
                      <td className="px-4 py-2">
                        <Badge value={p.sensitivity_classification} />
                      </td>
                      <td className="px-4 py-2 text-slate-600">
                        {p.permitted_audience.length > 0 ? p.permitted_audience.join(', ') : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <Section
          title="Pipeline & quality status"
          description={
            'The system does not currently track a separate "publication status" workflow — these are the ' +
            'real status signals it does track: pipeline stage and quality screening result, per data product.'
          }
        >
          {products && (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-2">Data product</th>
                    <th className="px-4 py-2">Pipeline stage</th>
                    <th className="px-4 py-2">Quality</th>
                    <th className="px-4 py-2">Last updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {products.map((p) => (
                    <tr key={p.id}>
                      <td className="px-4 py-2 font-medium text-slate-900">{p.title}</td>
                      <td className="px-4 py-2">
                        <Badge value={p.transformation_status} />
                      </td>
                      <td className="px-4 py-2">
                        <Badge value={p.quality_status} />
                      </td>
                      <td className="px-4 py-2 text-slate-500">{new Date(p.updated_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <Section title="Terminology mapping audit trail" description="Who reviewed each mapping, and when.">
          <RoleGate allow={['analyst', 'auditor']}>
            <TerminologyAuditTable />
          </RoleGate>
        </Section>

        <Section title="Raw record provenance" description="Unmodified source records ingested from DHIS2.">
          <RoleGate allow={['data_provider', 'auditor']}>
            <RawRecordsTable />
          </RoleGate>
        </Section>

        <Section
          title="Population data quality"
          description="Issues detected while reconciling census population data against DHIS2 districts (see the UHC District Service Coverage product)."
        >
          <RoleGate allow={['analyst', 'auditor']}>
            <PopulationIssuesTable />
          </RoleGate>
        </Section>
      </div>
    </div>
  )
}

function TerminologyAuditTable() {
  const { data, error, isLoading } = useApiResource<TerminologyMapping[]>('/api/core/terminology-mappings/')

  if (error?.status === 403) return <ForbiddenNotice roles={['analyst', 'auditor']} />
  if (error) return <p className="text-sm text-red-600">Could not load terminology mappings.</p>
  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Source</th>
            <th className="px-4 py-2">Target</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2">Reviewer</th>
            <th className="px-4 py-2">Reviewed</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data?.map((m) => (
            <tr key={m.id}>
              <td className="px-4 py-2 text-slate-900">
                {m.source_display} <span className="text-slate-400">({m.source_system}:{m.source_code})</span>
              </td>
              <td className="px-4 py-2 text-slate-600">
                {m.target_code ? `${m.target_terminology.toUpperCase()}:${m.target_code}` : '—'}
              </td>
              <td className="px-4 py-2">
                <Badge value={m.status} />
              </td>
              <td className="px-4 py-2 text-slate-600">{m.reviewer_username ?? '—'}</td>
              <td className="px-4 py-2 text-slate-500">
                {m.reviewed_at ? new Date(m.reviewed_at).toLocaleString() : '—'}
              </td>
            </tr>
          ))}
          {data?.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                No terminology mappings yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function PopulationIssuesTable() {
  const { data, error, isLoading } = useApiResource<PopulationDataQualityIssue[]>(
    '/api/core/population-data-quality-issues/',
  )

  if (error?.status === 403) return <ForbiddenNotice roles={['analyst', 'auditor']} />
  if (error) return <p className="text-sm text-red-600">Could not load population data-quality issues.</p>
  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Issue</th>
            <th className="px-4 py-2">District</th>
            <th className="px-4 py-2">Detail</th>
            <th className="px-4 py-2">Detected</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data?.map((issue) => (
            <tr key={issue.id}>
              <td className="px-4 py-2">
                <Badge value={issue.issue_type} />
              </td>
              <td className="px-4 py-2 text-slate-900">{issue.district_name || '—'}</td>
              <td className="px-4 py-2 text-slate-600">{issue.detail}</td>
              <td className="px-4 py-2 text-slate-500">{new Date(issue.detected_at).toLocaleString()}</td>
            </tr>
          ))}
          {data?.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-6 text-center text-slate-400">
                No data-quality issues detected.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function RawRecordsTable() {
  const { data, error, isLoading } = useApiResource<RawDHIS2Record[]>('/api/core/raw-records/')

  if (error?.status === 403) return <ForbiddenNotice roles={['data_provider', 'auditor']} />
  if (error) return <p className="text-sm text-red-600">Could not load raw records.</p>
  if (isLoading) return <p className="text-sm text-slate-500">Loading…</p>

  const shown = data?.slice(0, 50) ?? []

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Indicator</th>
            <th className="px-4 py-2">Org unit</th>
            <th className="px-4 py-2">Period</th>
            <th className="px-4 py-2">Value</th>
            <th className="px-4 py-2">Fetched</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {shown.map((r) => (
            <tr key={r.id}>
              <td className="px-4 py-2 text-slate-900">{r.dx_name}</td>
              <td className="px-4 py-2 text-slate-600">{r.org_unit_name}</td>
              <td className="px-4 py-2 text-slate-600">{r.period}</td>
              <td className="px-4 py-2 text-slate-600">{r.value}</td>
              <td className="px-4 py-2 text-slate-500">{new Date(r.fetched_at).toLocaleString()}</td>
            </tr>
          ))}
          {data?.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                No raw records yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {data && data.length > 50 && (
        <p className="border-t border-slate-100 px-4 py-2 text-xs text-slate-400">
          Showing the first 50 of {data.length} records.
        </p>
      )}
    </div>
  )
}
