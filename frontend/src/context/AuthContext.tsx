import React, { createContext, useContext, useEffect, useState } from 'react'
import { useAuth as useClerkAuth, useUser } from '@clerk/react'

interface AuthContextType {
  user: { id: string; email: string } | null
  loading: boolean
  role: string
  organizationId: string | null
  token: string | null
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isLoaded, isSignedIn, getToken, signOut: clerkSignOut } = useClerkAuth()
  const { user: clerkUser } = useUser()
  const [role, setRole] = useState('operator')
  const [organizationId, setOrganizationId] = useState<string | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [profileLoaded, setProfileLoaded] = useState(false)

  useEffect(() => {
    if (!isLoaded) return
    if (!isSignedIn) {
      setRole('operator')
      setOrganizationId(null)
      setToken(null)
      setProfileLoaded(true)
      return
    }
    fetchProfile()
  }, [isLoaded, isSignedIn])

  const fetchProfile = async () => {
    try {
      const t = await getToken()
      setToken(t)
      if (t) {
        const email = clerkUser?.primaryEmailAddress?.emailAddress ?? ''
        const res = await fetch('/api/profile', {
          headers: {
            Authorization: `Bearer ${t}`,
            'X-User-Email': email,
          },
        })
        if (res.ok) {
          const data = await res.json()
          setRole(data.role || 'operator')
          setOrganizationId(data.organization_id || null)
        }
      }
    } catch (err) {
      console.error('Profile fetch error:', err)
    } finally {
      setProfileLoaded(true)
    }
  }

  const user =
    isSignedIn && clerkUser
      ? { id: clerkUser.id, email: clerkUser.primaryEmailAddress?.emailAddress ?? '' }
      : null

  return (
    <AuthContext.Provider
      value={{
        user,
        loading: !isLoaded || (!!isSignedIn && !profileLoaded),
        role,
        organizationId,
        token,
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
