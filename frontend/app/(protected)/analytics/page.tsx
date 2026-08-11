import { AnalyticsTab, AnalyticsTabs } from '@/components/analytics/AnalyticsTabs'
import { ConformityView } from '@/components/analytics/ConformityView'
import { DistrictComparisonChart } from '@/components/analytics/DistrictComparisonChart'
import { ServiceCoverageView } from '@/components/analytics/ServiceCoverageView'
import { TrendChart } from '@/components/analytics/TrendChart'
import { RoleGate } from '@/components/RoleGate'

const tabs: AnalyticsTab[] = [
  {
    key: 'district-comparison',
    title: 'District comparison',
    description: 'Indicator value by district for a selected period.',
    content: (
      <RoleGate allow={['analyst', 'auditor']}>
        <DistrictComparisonChart />
      </RoleGate>
    ),
  },
  {
    key: 'trend',
    title: 'Trend over time',
    description: 'Indicator value across periods.',
    content: (
      <RoleGate allow={['analyst', 'auditor']}>
        <TrendChart />
      </RoleGate>
    ),
  },
  {
    key: 'conformity',
    title: 'Data quality & conformity',
    description: 'Data product quality screening and FHIR conformity check results.',
    content: <ConformityView />,
  },
  {
    key: 'service-coverage',
    title: 'Service coverage vs. population (UHC)',
    description:
      'Reported service activity as a share of district population — an insight that needs both DHIS2 and population data together.',
    content: (
      <RoleGate allow={['analyst', 'auditor']}>
        <ServiceCoverageView />
      </RoleGate>
    ),
  },
]

export default function AnalyticsPage() {
  return (
    <div>
      <h1 className="text-xl font-semibold text-slate-900">Analytics</h1>
      <p className="mt-1 text-sm text-slate-500">
        Geographic comparison, trend over time, and data-quality / conformity signals.
      </p>

      <div className="mt-6">
        <AnalyticsTabs tabs={tabs} />
      </div>
    </div>
  )
}
