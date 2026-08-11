import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
} from "./token-storage";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Dispatched when a refresh attempt fails, so AuthProvider (which owns
// the `me` state) can react without api-client importing React/context.
export const AUTH_EXPIRED_EVENT = "mediation:auth-expired";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  const response = await fetch(`${API_URL}/api/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!response.ok) return null;

  const data = await response.json();
  setAccessToken(data.access);
  return data.access as string;
}

async function doFetch(
  path: string,
  init: RequestInit,
  token: string | null,
): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

/** Authenticated fetch: attaches the access token, retries once via a
 * silent refresh on 401, and throws ApiError (with .status) otherwise so
 * callers/SWR can distinguish "forbidden for your role" (403) from other
 * failures. */
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let response = await doFetch(path, init, getAccessToken());

  if (response.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      response = await doFetch(path, init, newToken);
    } else {
      clearTokens();
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
      throw new ApiError(401, "Session expired");
    }
  }

  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = body.detail ?? JSON.stringify(body);
    } catch {
      // response body wasn't JSON - keep statusText
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// ---- Response shapes (mirrors the real DRF serializers only - no
// fields exist here that the backend doesn't actually return). ----

export interface District {
  id: number;
  dhis2_org_unit_uid: string;
  name: string;
}

export interface Indicator {
  id: number;
  dhis2_dx_uid: string;
  name: string;
  description: string;
}

export interface Observation {
  id: number;
  indicator: Indicator;
  district: District;
  period: string;
  /** FR6.7: small-cell suppressed - generalised to the suppression
   * threshold (never the true value) when is_suppressed is true. */
  value: number;
  is_suppressed: boolean;
  source_raw_record: number;
}

export type SensitivityClassification =
  | "public"
  | "internal"
  | "sensitive"
  | "personal"
  | "potentially_identifying"
  | "prohibited";
export type TransformationStatus = "raw_only" | "canonical" | "fhir_mapped";
export type QualityStatus =
  | "unscreened"
  | "publishable"
  | "publishable_with_warnings"
  | "blocked";

export interface DataProductSource {
  id: number;
  name: string;
  description: string;
  extraction_date: string | null;
  reference_period: string;
}

// FR6.6: how much a "passed" should be trusted without re-checking it -
// deterministic (a hard fact), heuristic (a statistical judgement call,
// can have false positives), or human_required (never evaluated by code,
// reads a decision a data steward already made).
export type QualityCheckMethod =
  | "deterministic"
  | "heuristic"
  | "human_required";
export type QualityCheckSeverity = "info" | "warning" | "blocker";

export interface QualityCheckResult {
  id: number;
  check_code: string;
  check_name: string;
  method: QualityCheckMethod;
  severity: QualityCheckSeverity;
  passed: boolean;
  detail: string;
  checked_at: string;
}

export interface DataProduct {
  id: number;
  title: string;
  purpose: string;
  data_owner: string;
  source: string;
  refresh_date: string | null;
  geographic_coverage: string;
  temporal_coverage_start: string;
  temporal_coverage_end: string;
  schema_version: string;
  sensitivity_classification: SensitivityClassification;
  transformation_status: TransformationStatus;
  quality_status: QualityStatus;
  // FR6.6 human-approval gate: a data steward has reviewed sensitivity_classification
  // and permitted_audience. Never true until a human sets it via the admin.
  governance_reviewed: boolean;
  quality_checks: QualityCheckResult[];
  permitted_audience: string[];
  // Null for cross-indicator, cross-source products (e.g. UHC District Service Coverage).
  indicator: Indicator | null;
  join_strategy: string;
  transformation_description: string;
  sources: DataProductSource[];
  updated_at: string;
}

export interface FHIRValidationIssue {
  severity: string;
  diagnostics?: string;
}

export interface FHIRValidationResult {
  id: number;
  resource_type: string;
  resource_reference: string;
  fhir_json: unknown;
  fhir_release: string;
  validator_used: string;
  is_valid: boolean;
  issues: FHIRValidationIssue[];
  validated_at: string;
}

export type TerminologyStatus =
  | "proposed"
  | "accepted"
  | "rejected"
  | "unmapped";

export interface TerminologyMapping {
  id: number;
  source_system: string;
  source_code: string;
  source_display: string;
  target_terminology: string;
  target_code: string;
  target_display: string;
  terminology_version: string;
  status: TerminologyStatus;
  mapping_method: string;
  confidence: number | null;
  rationale: string;
  reviewer: number | null;
  reviewer_username: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RawDHIS2Record {
  id: number;
  dx_uid: string;
  dx_name: string;
  org_unit_uid: string;
  org_unit_name: string;
  period: string;
  value: string;
  raw_payload: unknown;
  source_url: string;
  fetched_at: string;
}

export interface DistrictPopulation {
  id: number;
  district: District;
  total_population: number;
  reference_year: number;
  source_record_count: number;
  updated_at: string;
}

export type PopulationIssueType =
  | "missing_population"
  | "missing_dhis2_observation"
  | "unknown_district"
  | "duplicate_record"
  | "conflicting_identifier"
  | "out_of_period"
  | "stale_data";

export interface PopulationDataQualityIssue {
  id: number;
  issue_type: PopulationIssueType;
  district_name: string;
  detail: string;
  detected_at: string;
}

export interface ServiceCoverageRow {
  district_id: number;
  district: string;
  population: number | null;
  service_activity: number | null;
  ratio_percent: number | null;
  excluded: boolean;
  excluded_reason: string;
  potentially_underserved: boolean;
}

// FR6.8: the audit trail. AuditEvent = who did what to the system (access/
// security activity); ProvenanceRecord = how a dataset's content came to
// be (data lineage) - see docs/audit.md for the full distinction.
export type AuditAction =
  | "authentication"
  | "access_denied"
  | "data_acquisition"
  | "data_transformation"
  | "data_validation"
  | "dataset_publication"
  | "dataset_view"
  | "dataset_download"
  | "admin_change";
export type AuditOutcome = "success" | "denied" | "failure";

export interface AuditEvent {
  id: number;
  actor: string;
  organisation: string;
  action: AuditAction;
  resource_type: string;
  resource_id: string;
  outcome: AuditOutcome;
  correlation_id: string;
  detail: Record<string, unknown>;
  timestamp: string;
}

export type ProvenanceActivity =
  | "acquired"
  | "transformed"
  | "validated"
  | "derived";

export interface ProvenanceRecord {
  id: number;
  data_product: number | null;
  resource_type: string;
  resource_id: string;
  activity: ProvenanceActivity;
  description: string;
  source_reference: string;
  performed_by: string;
  correlation_id: string;
  occurred_at: string;
}

export interface ServiceCoverageResponse {
  indicator: string | null;
  period: string | null;
  reference_year: number | null;
  rows: ServiceCoverageRow[];
  caveat: string;
}
