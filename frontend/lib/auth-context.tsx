'use client'

import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react'

import { API_URL, apiFetch, ApiError, AUTH_EXPIRED_EVENT } from './api-client'
import { clearTokens, getAccessToken, setTokens } from './token-storage'

export interface Me {
  username: string
  roles: string[]
  is_staff: boolean
}

interface AuthContextValue {
  me: Me | null
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const loadMe = useCallback(async () => {
    try {
      const result = await apiFetch<Me>('/api/auth/me/')
      setMe(result)
    } catch {
      setMe(null)
    }
  }, [])

  useEffect(() => {
    const init = async () => {
      if (getAccessToken()) {
        await loadMe()
      }
      setIsLoading(false)
    }
    init()

    const handleExpired = () => setMe(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired)
  }, [loadMe])

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await fetch(`${API_URL}/api/auth/token/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (!response.ok) {
        throw new ApiError(response.status, 'Invalid username or password')
      }
      const data = await response.json()
      setTokens(data.access, data.refresh)
      await loadMe()
    },
    [loadMe],
  )

  const logout = useCallback(() => {
    clearTokens()
    setMe(null)
  }, [])

  return <AuthContext.Provider value={{ me, isLoading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
