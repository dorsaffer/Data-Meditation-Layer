'use client'

import { ReactNode, useEffect } from 'react'
import { useRouter } from 'next/navigation'

import { useAuth } from '@/lib/auth-context'
import { TopNav } from '@/components/TopNav'

export default function ProtectedLayout({ children }: { children: ReactNode }) {
  const { me, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && !me) router.replace('/login')
  }, [isLoading, me, router])

  if (isLoading) {
    return <div className="p-8 text-sm text-slate-500">Loading…</div>
  }

  if (!me) return null

  return (
    <div className="min-h-screen bg-slate-50">
      <TopNav />
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  )
}
