const COLOR_MAP: Record<string, string> = {
  // sensitivity_classification (FR6.7 taxonomy, ordered least -> most restrictive)
  public: 'bg-emerald-100 text-emerald-800',
  internal: 'bg-sky-100 text-sky-800',
  sensitive: 'bg-amber-100 text-amber-800',
  personal: 'bg-orange-100 text-orange-800',
  potentially_identifying: 'bg-red-100 text-red-800',
  prohibited: 'bg-red-200 text-red-900',
  // quality_status (FR6.6 publication decision) / fhir validity
  passed: 'bg-emerald-100 text-emerald-800',
  publishable: 'bg-emerald-100 text-emerald-800',
  publishable_with_warnings: 'bg-amber-100 text-amber-800',
  blocked: 'bg-red-100 text-red-800',
  flagged: 'bg-red-100 text-red-800',
  unscreened: 'bg-slate-100 text-slate-700',
  // quality check method / severity
  deterministic: 'bg-sky-100 text-sky-800',
  heuristic: 'bg-violet-100 text-violet-800',
  human_required: 'bg-amber-100 text-amber-800',
  info: 'bg-slate-100 text-slate-700',
  warning: 'bg-amber-100 text-amber-800',
  blocker: 'bg-red-100 text-red-800',
  // transformation_status
  raw_only: 'bg-slate-100 text-slate-700',
  canonical: 'bg-sky-100 text-sky-800',
  fhir_mapped: 'bg-violet-100 text-violet-800',
  // terminology status
  proposed: 'bg-amber-100 text-amber-800',
  accepted: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  unmapped: 'bg-slate-100 text-slate-700',
  // population data-quality issue types
  missing_population: 'bg-red-100 text-red-800',
  missing_dhis2_observation: 'bg-amber-100 text-amber-800',
  unknown_district: 'bg-slate-100 text-slate-700',
  duplicate_record: 'bg-red-100 text-red-800',
  conflicting_identifier: 'bg-red-100 text-red-800',
  out_of_period: 'bg-amber-100 text-amber-800',
  stale_data: 'bg-amber-100 text-amber-800',
  // FR6.8 AuditEvent outcome
  success: 'bg-emerald-100 text-emerald-800',
  denied: 'bg-red-100 text-red-800',
  failure: 'bg-red-100 text-red-800',
}

export function Badge({ value }: { value: string }) {
  const className = COLOR_MAP[value] ?? 'bg-slate-100 text-slate-700'
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {value.replace(/_/g, ' ')}
    </span>
  )
}
