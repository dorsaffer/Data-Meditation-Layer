const COLOR_MAP: Record<string, string> = {
  // sensitivity_classification
  public: 'bg-emerald-100 text-emerald-800',
  restricted: 'bg-amber-100 text-amber-800',
  confidential: 'bg-red-100 text-red-800',
  // quality_status / fhir validity
  passed: 'bg-emerald-100 text-emerald-800',
  flagged: 'bg-red-100 text-red-800',
  unscreened: 'bg-slate-100 text-slate-700',
  // transformation_status
  raw_only: 'bg-slate-100 text-slate-700',
  canonical: 'bg-sky-100 text-sky-800',
  fhir_mapped: 'bg-violet-100 text-violet-800',
  // terminology status
  proposed: 'bg-amber-100 text-amber-800',
  accepted: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  unmapped: 'bg-slate-100 text-slate-700',
}

export function Badge({ value }: { value: string }) {
  const className = COLOR_MAP[value] ?? 'bg-slate-100 text-slate-700'
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {value.replace(/_/g, ' ')}
    </span>
  )
}
