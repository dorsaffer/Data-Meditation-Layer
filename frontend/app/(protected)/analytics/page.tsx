import { ReactNode } from 'react'

import { ConformityView } from '@/components/analytics/ConformityView'
import { DistrictComparisonChart } from '@/components/analytics/DistrictComparisonChart'
import { ServiceCoverageView } from '@/components/analytics/ServiceCoverageView'
import { TrendChart } from '@/components/analytics/TrendChart'
import { RoleGate } from '@/components/RoleGate'

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6">
      <h2 className="text-base font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 text-sm text-slate-500">{description}</p>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export default function AnalyticsPage() {
  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-900">Analytics</h1>
      <p className="mt-1 text-sm text-slate-500">
        Geographic comparison, trend over time, and data-quality / conformity signals.
      </p>

      <div className="mt-6 space-y-6">
        <Section title="District comparison" description="Indicator value by district for a selected period.">
          <RoleGate allow={['analyst', 'auditor']}>
            <DistrictComparisonChart />
          </RoleGate>
        </Section>

        <Section title="Trend over time" description="Indicator value across periods.">
          <RoleGate allow={['analyst', 'auditor']}>
            <TrendChart />
          </RoleGate>
        </Section>

        <Section
          title="Data quality & conformity"
          description="Data product quality screening and FHIR conformity check results."
        >
          <ConformityView />
        </Section>

        <Section
          title="Service coverage vs. population (UHC)"
          description="Reported service activity as a share of district population — an insight that needs both DHIS2 and population data together."
        >
          <RoleGate allow={['analyst', 'auditor']}>
            <ServiceCoverageView />
          </RoleGate>
        </Section>
      </div>
    </div>
  )
}
