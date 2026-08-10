import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'SL Health Mediation Layer',
  description: 'Sierra Leone health data mediation layer',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
