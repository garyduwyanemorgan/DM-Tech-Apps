import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { useAuth as useClerkAuth, useUser } from '@clerk/react'

interface AuthContextType {
  user: { id: string; email: string } | null
  loading: boolean
  role: string
  organizationId: string | null
  token: string | null
  /** Fetch a FRESH Clerk session token. Use this for authenticated writes —
   *  the cached `token` can expire (Clerk tokens live ~60s). */
  getToken: () => Promise<string | null>
  email: string
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

// Clerk session tokens expire ~60s; refresh comfortably inside that window.
const TOKEN_REFRESH_MS = 45_000

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isLoaded, isSignedIn, getToken: clerkGetToken, signOut: clerkSignOut } = useClerkAuth()
  const { user: clerkUser } = useUser()
  const [role, setRole] = useState('operator')
  const [organizationId, setOrganizationId] = useState<string | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [profileLoaded, setProfileLoaded] = useState(false)

  const email = clerkUser?.primaryEmailAddress?.emailAddress ?? ''

  useEffect(() => {
    if (!isLoaded) return
    if (!isSignedIn) {
      setRole('operator')
      setOrganizationId(null)
      setToken(null)
      setProfileLoaded(true)
      return
    }

    let cancelled = false

    const refresh = async (): Promise<string | null> => {
      try {
        const t = await clerkGetToken()
        if (!cancelled) setToken(t)
        return t
      } catch {
        return null
      }
    }

    const loadProfile = async (t: string | null) => {
      if (!t) return
      try {
        const res = await fetch('/api/profile', {
          headers: { Authorization: `Bearer ${t}`, 'X-User-Email': email },
        })
        if (res.ok && !cancelled) {
          const data = await res.json()
          setRole(data.role || 'operator')
          setOrganizationId(data.organization_id || null)
        }
      } catch (err) {
        console.error('Profile fetch error:', err)
      }
    }

    void (async () => {
      const t = await refresh()
      await loadProfile(t)
      if (!cancelled) setProfileLoaded(true)
    })()

    // Keep the cached token fresh so authenticated writes never send a stale token.
    const id = setInterval(refresh, TOKEN_REFRESH_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, isSignedIn, email])

  // Always returns a fresh token (Clerk caches/rotates internally) and syncs state.
  const getToken = useCallback(async (): Promise<string | null> => {
    try {
      const t = await clerkGetToken()
      setToken(t)
      return t
    } catch {
      return null
    }
  }, [clerkGetToken])

  const user = isSignedIn && clerkUser ? { id: clerkUser.id, email } : null

  return (
    <AuthContext.Provider
      value={{
        user,
        loading: !isLoaded || (!!isSignedIn && !profileLoaded),
        role,
        organizationId,
        token,
        getToken,
        email,
        signOut: clerkSignOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
