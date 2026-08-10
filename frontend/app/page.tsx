'use client'

import { useEffect, useState } from 'react'

export default function Home() {
  const [status, setStatus] = useState<string>('checking…')

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    fetch(`${apiUrl}/api/health/`)
      .then((r) => r.json())
      .then((d) => setStatus(d.status))
      .catch(() => setStatus('unreachable'))
  }, [])

  return (
    <main style={{ fontFamily: 'monospace', padding: '2rem' }}>
      <h1>SL Health Mediation Layer</h1>
      <p>Backend: <strong>{status}</strong></p>
    </main>
  )
}
