'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'

import { useAuth } from '@/lib/auth-context'

const NAV_ITEMS: { href: string; label: string; roles: string[] }[] = [
  { href: '/products', label: 'Catalog', roles: ['data_provider', 'analyst', 'auditor'] },
  { href: '/analytics', label: 'Analytics', roles: ['analyst', 'auditor'] },
  { href: '/governance', label: 'Governance', roles: ['data_provider', 'analyst', 'auditor'] },
]

export function TopNav() {
  const { me, logout } = useAuth()
  const pathname = usePathname()
  const router = useRouter()

  if (!me) return null

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  const visibleItems = NAV_ITEMS.filter(
    (item) => me.is_staff || item.roles.some((role) => me.roles.includes(role)),
  )

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-8">
          <span className="font-semibold text-slate-900">SL Health Mediation Layer</span>
          <nav className="flex gap-1 text-sm">
            {visibleItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded px-3 py-1.5 ${
                  pathname?.startsWith(item.href)
                    ? 'bg-slate-900 text-white'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-600">{me.username}</span>
          <div className="flex gap-1">
            {me.roles.map((role) => (
              <span key={role} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                {role.replace(/_/g, ' ')}
              </span>
            ))}
            {me.roles.length === 0 && (
              <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">no role</span>
            )}
          </div>
          <button
            onClick={handleLogout}
            className="rounded border border-slate-300 px-2 py-1 text-slate-600 hover:bg-slate-100"
          >
            Log out
          </button>
        </div>
      </div>
    </header>
  )
}
