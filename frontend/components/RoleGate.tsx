'use client'

import { ReactNode } from 'react'

import { useAuth } from '@/lib/auth-context'

import { ForbiddenNotice } from './ForbiddenNotice'

/** UX-only gating: hides a section the backend would 403 on for the
 * current user's role, so the page doesn't render a dead-end request.
 * The real enforcement is server-side (see docs/rbac.md) - this is
 * purely to avoid showing a control nobody can use. */
export function RoleGate({ allow, children }: { allow: string[]; children: ReactNode }) {
  const { me } = useAuth()
  if (!me) return null

  const hasAccess = me.is_staff || me.roles.some((role) => allow.includes(role))
  if (!hasAccess) return <ForbiddenNotice roles={allow} />

  return <>{children}</>
}
