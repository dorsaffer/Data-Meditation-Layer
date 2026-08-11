import type { Metadata } from 'next'

import { AuthProvider } from '@/lib/auth-context'

import './globals.css'

export const metadata: Metadata = {
  title: 'SL Health Mediation Layer',
  description: 'Sierra Leone health data mediation layer',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
