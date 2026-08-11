'use client'

import { FormEvent, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { useAuth } from '@/lib/auth-context'

export default function LoginPage() {
  const { login, me } = useAuth()
  const router = useRouter()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (me) router.replace('/products')
  }, [me, router])

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(username, password)
      router.replace('/products')
    } catch {
      setError('Invalid username or password.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm"
      >
        <h1 className="mb-1 text-lg font-semibold text-slate-900">SL Health Mediation Layer</h1>
        <p className="mb-6 text-sm text-slate-500">
          Sign in to view the data product catalog, analytics and governance views.
        </p>

        {error && <p className="mb-4 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        <label className="mb-3 block text-sm">
          <span className="mb-1 block text-slate-700">Username</span>
          <input
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label className="mb-6 block text-sm">
          <span className="mb-1 block text-slate-700">Password</span>
          <input
            type="password"
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
