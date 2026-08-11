import { clearTokens, getAccessToken, getRefreshToken, setAccessToken } from './token-storage'

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// Dispatched when a refresh attempt fails, so AuthProvider (which owns
// the `me` state) can react without api-client importing React/context.
export const AUTH_EXPIRED_EVENT = 'mediation:auth-expired'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken()
  if (!refresh) return null

  const response = await fetch(`${API_URL}/api/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  if (!response.ok) return null

  const data = await response.json()
  setAccessToken(data.access)
  return data.access as string
}

async function doFetch(path: string, init: RequestInit, token: string | null): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
}

/** Authenticated fetch: attaches the access token, retries once via a
 * silent refresh on 401, and throws ApiError (with .status) otherwise so
 * callers/SWR can distinguish "forbidden for your role" (403) from other
 * failures. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await doFetch(path, init, getAccessToken())

  if (response.status === 401) {
    const newToken = await refreshAccessToken()
    if (newToken) {
      response = await doFetch(path, init, newToken)
    } else {
      clearTokens()
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
      throw new ApiError(401, 'Session expired')
    }
  }

  if (!response.ok) {
    let message = response.statusText
    try {
      const body = await response.json()
      message = body.detail ?? JSON.stringify(body)
    } catch {
      // response body wasn't JSON - keep statusText
    }
    throw new ApiError(response.status, message)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

// ---- Response shapes (mirrors the real DRF serializers only - no
// fields exist here that the backend doesn't actually return). ----

export interface District {
  id: number
  dhis2_org_unit_uid: string
  name: string
}

export interface Indicator {
  id: number
  dhis2_dx_uid: string
  name: string
  description: string
}

export interface Observation {
  id: number
  indicator: Indicator
  district: District
  period: string
  value: number
  source_raw_record: number
}

export type SensitivityClassification = 'public' | 'restricted' | 'confidential'
export type TransformationStatus = 'raw_only' | 'canonical' | 'fhir_mapped'
export type QualityStatus = 'unscreened' | 'passed' | 'flagged'

export interface DataProduct {
  id: number
  title: string
  purpose: string
  data_owner: string
  source: string
  refresh_date: string | null
  geographic_coverage: string
  temporal_coverage_start: string
  temporal_coverage_end: string
  schema_version: string
  sensitivity_classification: SensitivityClassification
  transformation_status: TransformationStatus
  quality_status: QualityStatus
  permitted_audience: string[]
  indicator: Indicator
  updated_at: string
}

export interface FHIRValidationIssue {
  severity: string
  diagnostics?: string
}

export interface FHIRValidationResult {
  id: number
  resource_type: string
  resource_reference: string
  fhir_json: unknown
  fhir_release: string
  validator_used: string
  is_valid: boolean
  issues: FHIRValidationIssue[]
  validated_at: string
}

export type TerminologyStatus = 'proposed' | 'accepted' | 'rejected' | 'unmapped'

export interface TerminologyMapping {
  id: number
  source_system: string
  source_code: string
  source_display: string
  target_terminology: string
  target_code: string
  target_display: string
  terminology_version: string
  status: TerminologyStatus
  mapping_method: string
  confidence: number | null
  rationale: string
  reviewer: number | null
  reviewer_username: string | null
  reviewed_at: string | null
  created_at: string
  updated_at: string
}

export interface RawDHIS2Record {
  id: number
  dx_uid: string
  dx_name: string
  org_unit_uid: string
  org_unit_name: string
  period: string
  value: string
  raw_payload: unknown
  source_url: string
  fetched_at: string
}
