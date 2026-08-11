'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

import { useAuth } from '@/lib/auth-context'

export default function Home() {
  const { me, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (isLoading) return
    router.replace(me ? '/products' : '/login')
  }, [isLoading, me, router])

  return <p className="p-8 text-sm text-slate-500">Loading…</p>
}
