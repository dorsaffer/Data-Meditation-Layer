'use client'

import useSWR from 'swr'

import { apiFetch, ApiError } from '../api-client'
import { useAuth } from '../auth-context'

/** Generic authenticated-resource hook shared by every page - one SWR
 * fetcher for all endpoints rather than a near-duplicate hook per
 * resource. `error.status === 403` lets callers show a role-specific
 * "not visible to your role" state instead of a generic failure. */
export function useApiResource<T>(path: string | null) {
  const { me } = useAuth()
  const key = me && path ? path : null
  const { data, error, isLoading } = useSWR<T, ApiError>(key, (p: string) => apiFetch<T>(p))

  return {
    data,
    error,
    isLoading,
    isForbidden: error instanceof ApiError && error.status === 403,
  }
}
