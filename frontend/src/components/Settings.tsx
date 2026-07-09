import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { PageHeader } from './PageHeader'
import { SiteManager } from './SiteManager'
import { UserManager } from './UserManager'

interface SettingsProps {
  useSampleData: boolean
  setUseSampleData: (v: boolean) => void
  activeSite: string
  setActiveSite: (s: string) => void
}

interface BillingStatus {
  plan: string
  plan_name: string
  plan_description: string
  site_limit: number
  sites_used: number
  can_add_site: boolean
  has_subscription: boolean
  payments_configured: boolean
  portal_available: boolean
  payment_provider: string
  available_plans: Record<string, { name: string; site_limit: number; price_usd: number; description: string }>
}

const Toggle: React.FC<{ value: boolean; onChange: (v: boolean) => void }> = ({ value, onChange }) => (
  <div
    role="switch"
    aria-checked={value}
    onClick={() => onChange(!value)}
    style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: '0.5rem', userSelect: 'none' }}
  >
    <div style={{
      width: '44px', height: '24px', borderRadius: '12px',
      background: value ? '#2E5D8A' : '#cbd5e1',
      position: 'relative', transition: 'background 0.2s', flexShrink: 0,
    }}>
      <div style={{
        position: 'absolute', top: '3px', left: value ? '23px' : '3px',
        width: '18px', height: '18px', borderRadius: '50%',
        background: '#ffffff', boxShadow: '0 1px 4px rgba(0,0,0,0.2)', transition: 'left 0.2s',
      }} />
    </div>
    <span style={{ fontSize: '0.875rem', fontWeight: 600, color: value ? '#1B3A5C' : '#94a3b8' }}>
      {value ? 'Enabled' : 'Disabled'}
    </span>
  </div>
)

const PLAN_COLORS: Record<string, { bg: string; color: string; border: string }> = {
  starter:      { bg: '#f1f5f9',  color: '#475569',  border: '#e2e8f0' },
  growth:       { bg: '#D6E4F0',  color: '#1B3A5C',  border: '#93c5fd' },
  professional: { bg: '#C6EFCE',  color: '#006100',  border: '#86efac' },
  dev:          { bg: '#FFEB9C',  color: '#856404',  border: '#fcd34d' },
}

const BillingPanel: React.FC<{ organizationId: string | null; token: string | null }> = ({ organizationId, token }) => {
  const [status, setStatus] = useState<BillingStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [checkingOut, setCheckingOut] = useState<string | null>(null)
  const [openingPortal, setOpeningPortal] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const headers = (): HeadersInit => {
    const h: HeadersInit = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }

  const loadStatus = async () => {
    try {
      const res = await fetch('/api/billing/status', { headers: headers() })
      if (res.ok) setStatus(await res.json())
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  useEffect(() => { loadStatus() }, [organizationId])

  const handleUpgrade = async (planKey: string) => {
    setCheckingOut(planKey)
    setError(null)
    try {
      const res = await fetch('/api/billing/checkout', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({
          plan: planKey,
          success_url: `${window.location.origin}/?billing=success`,
          cancel_url: `${window.location.origin}/?billing=cancelled`,
        }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Checkout failed.'); return }
      window.location.href = data.checkout_url
    } catch { setError('Network error. Try again.') }
    finally { setCheckingOut(null) }
  }

  const handlePortal = async () => {
    setOpeningPortal(true)
    setError(null)
    try {
      const res = await fetch('/api/billing/portal', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ return_url: window.location.origin }),
      })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Could not open billing portal.'); return }
      window.location.href = data.portal_url
    } catch { setError('Network error. Try again.') }
    finally { setOpeningPortal(false) }
  }

  const handleCancel = async () => {
    if (!window.confirm('Cancel your subscription? Your organization will be downgraded to the Starter plan.')) return
    setCancelling(true)
    setError(null)
    try {
      const res = await fetch('/api/billing/cancel', { method: 'POST', headers: headers() })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Cancellation failed.'); return }
      await loadStatus()
    } catch { setError('Network error. Try again.') }
    finally { setCancelling(false) }
  }

  if (loading) return (
    <div style={{ padding: '1.5rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.875rem' }}>
      Loading billing status…
    </div>
  )

  if (!status) return null

  // Defensive defaults — a partial backend response must never crash the Settings page
  const planName = status.plan_name || 'No Plan'
  const planDescription = status.plan_description || ''
  const availablePlans = status.available_plans || {}

  const pc = PLAN_COLORS[status.plan] || PLAN_COLORS.starter
  const usedPct = Math.min(100, status.site_limit > 0 ? (status.sites_used / status.site_limit) * 100 : 100)
  const atLimit = !status.can_add_site

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

      {error && (
        <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem' }}>
          {error}
        </div>
      )}

      {/* Current plan summary */}
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 240, background: '#f8fafc', border: `1px solid ${pc.border}`, borderRadius: 10, padding: '1rem 1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.5rem' }}>
            <span style={{ background: pc.bg, color: pc.color, fontWeight: 700, fontSize: '0.78rem', borderRadius: 4, padding: '2px 10px', border: `1px solid ${pc.border}` }}>
              {planName.toUpperCase()}
            </span>
            {status.has_subscription && (
              <span style={{ fontSize: '0.72rem', color: '#27ae60', fontWeight: 600 }}>● Active</span>
            )}
          </div>
          <div style={{ fontSize: '0.82rem', color: '#64748b', marginBottom: '1rem', lineHeight: 1.5 }}>
            {planDescription}
          </div>

          {/* Site usage bar */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: '#64748b', marginBottom: '4px' }}>
              <span>Sites used</span>
              <span style={{ fontWeight: 700, color: atLimit ? '#9C0006' : '#1B3A5C' }}>
                {status.sites_used} / {status.site_limit === 999 ? '∞' : status.site_limit}
              </span>
            </div>
            <div style={{ height: 8, borderRadius: 4, background: '#e2e8f0', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${usedPct}%`,
                borderRadius: 4,
                background: atLimit ? '#e74c3c' : usedPct > 70 ? '#f59e0b' : '#27ae60',
                transition: 'width 0.4s',
              }} />
            </div>
            {atLimit && (
              <div style={{ marginTop: '0.4rem', fontSize: '0.75rem', color: '#9C0006', fontWeight: 600 }}>
                Site limit reached — upgrade to add more lagoons.
              </div>
            )}
          </div>
        </div>

        {/* Manage billing — hosted portal when the provider offers one,
            otherwise a direct cancel action */}
        {status.has_subscription && (status.portal_available ? (
          <button
            onClick={handlePortal}
            disabled={openingPortal}
            className="secondary"
            style={{ alignSelf: 'flex-start', padding: '0.5rem 1rem', fontSize: '0.875rem' }}
          >
            {openingPortal ? 'Opening…' : '⚙ Manage Billing'}
          </button>
        ) : (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="secondary"
            style={{ alignSelf: 'flex-start', padding: '0.5rem 1rem', fontSize: '0.875rem' }}
          >
            {cancelling ? 'Cancelling…' : 'Cancel Subscription'}
          </button>
        ))}
      </div>

      {/* Plan cards — always visible */}
      <div>
        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.75rem' }}>
          Available Plans
        </div>

        {!status.payments_configured && (
          <div style={{ background: '#FFEB9C', color: '#856404', padding: '0.75rem 1rem', borderRadius: 8, fontSize: '0.82rem', border: '1px solid #fcd34d', lineHeight: 1.6, marginBottom: '0.75rem' }}>
            <strong>Payments not configured.</strong> Add your payment provider API keys to{' '}
            <code style={{ background: 'rgba(0,0,0,0.06)', padding: '1px 5px', borderRadius: 3 }}>.streamlit/secrets.toml</code>{' '}
            to enable purchases. Site limits are still enforced.
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
          {Object.entries(availablePlans)
            .filter(([key]) => key !== 'dev')
            .map(([key, plan]) => {
              const isCurrent = key === status.plan
              const pc2 = PLAN_COLORS[key] || PLAN_COLORS.starter
              return (
                <div key={key} style={{
                  border: `2px solid ${isCurrent ? pc2.border : '#e2e8f0'}`,
                  borderRadius: 10,
                  padding: '1rem',
                  background: isCurrent ? pc2.bg : '#fff',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.5rem',
                }}>
                  <div style={{ fontWeight: 700, color: isCurrent ? pc2.color : '#1B3A5C', fontSize: '1rem' }}>
                    {plan.name}
                  </div>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#1B3A5C' }}>
                    ${plan.price_usd}<span style={{ fontSize: '0.8rem', fontWeight: 500, color: '#64748b' }}>/mo</span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#64748b', lineHeight: 1.5, flex: 1 }}>
                    {plan.description}
                  </div>
                  {isCurrent ? (
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: pc2.color, textAlign: 'center' }}>
                      ✓ Current Plan
                    </span>
                  ) : status.payments_configured ? (
                    <button
                      onClick={() => handleUpgrade(key)}
                      disabled={!!checkingOut}
                      style={{ fontSize: '0.82rem', padding: '0.4rem 0.75rem' }}
                    >
                      {checkingOut === key ? 'Redirecting…' : 'Upgrade →'}
                    </button>
                  ) : (
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8', textAlign: 'center' }}>
                      Payment provider required to upgrade
                    </span>
                  )}
                </div>
              )
            })}
        </div>
      </div>
    </div>
  )
}

const APP_VERSION = import.meta.env.VITE_APP_VERSION
const BUILD_TIME = import.meta.env.VITE_BUILD_TIME

interface VersionInfo {
  version: string
  commit: string | null
  environment: string
}

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem', padding: '0.45rem 0' }}>
    <span style={{ fontSize: '0.82rem', color: '#64748b' }}>{label}</span>
    <span style={{ fontSize: '0.82rem', fontWeight: 600, color: '#1B3A5C', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
      {children}
    </span>
  </div>
)

/** Which build is actually running. `APP_VERSION` is stamped in at build time; the API reports the version of the process serving it. A
 *  mismatch means a cached or half-deployed SPA is talking to a newer backend. */
const AboutPanel: React.FC = () => {
  const [api, setApi] = useState<VersionInfo | null>(null)
  const [unreachable, setUnreachable] = useState(false)

  useEffect(() => {
    fetch('/api/version')
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then(setApi)
      .catch(() => setUnreachable(true))
  }, [])

  const buildTime = new Date(BUILD_TIME)
  const mismatch = api && api.version !== APP_VERSION

  return (
    <div>
      <Row label="App version">v{APP_VERSION}</Row>
      <Row label="API version">
        {unreachable ? <span style={{ color: '#9C0006' }}>unreachable</span> : api ? `v${api.version}` : '…'}
      </Row>
      {api?.commit && <Row label="Commit">{api.commit}</Row>}
      {api?.environment && <Row label="Environment">{api.environment}</Row>}
      <Row label="Built">{buildTime.toLocaleString()}</Row>

      {mismatch && (
        <div style={{ marginTop: '0.75rem', background: '#FFEB9C', color: '#856404', border: '1px solid #fcd34d', borderRadius: 8, padding: '0.75rem 1rem', fontSize: '0.8rem', lineHeight: 1.6 }}>
          <strong>Version mismatch.</strong> This page was built from v{APP_VERSION} but the
          server is running v{api.version}. Hard-refresh (Ctrl/⌘ + Shift + R) to load the current build.
        </div>
      )}
    </div>
  )
}

export const Settings: React.FC<SettingsProps> = ({ useSampleData, setUseSampleData, activeSite, setActiveSite }) => {
  const { role, organizationId, token } = useAuth()
  const isAdmin = role === 'admin' || role === 'super_admin'

  return (
    <div style={{ maxWidth: 960 }}>
      <PageHeader title="Settings" subtitle="Platform configuration, billing, and administration" icon="⚙️" />

      {/* Billing — admin only */}
      {isAdmin && (
        <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
          <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1.25rem' }}>
            Subscription &amp; Billing
          </h3>
          <BillingPanel organizationId={organizationId} token={token} />
        </div>
      )}

      {/* Data & Display */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1rem' }}>Data &amp; Display</h3>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '1rem', background: '#f8fafc', border: '1px solid #e2e8f0',
          borderRadius: '8px', gap: '1rem', flexWrap: 'wrap',
        }}>
          <div>
            <div style={{ fontWeight: 600, color: '#1B3A5C', marginBottom: '2px' }}>Sample / Demo Data</div>
            <div style={{ fontSize: '0.82rem', color: '#64748b', lineHeight: 1.5 }}>
              Show built-in demonstration readings alongside live data. Disable for live production deployments.
            </div>
          </div>
          <Toggle value={useSampleData} onChange={setUseSampleData} />
        </div>
        <div style={{ marginTop: '0.75rem', fontSize: '0.78rem', color: '#94a3b8', lineHeight: 1.5 }}>
          Saved in your browser — only affects your session.
        </div>
      </div>

      {/* Site Manager — admin only */}
      {isAdmin && (
        <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
          <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1.25rem' }}>Site Management</h3>
          <SiteManager activeSite={activeSite} setActiveSite={setActiveSite} onSitesChanged={() => {}} embedded />
        </div>
      )}

      {/* User Management — admin only */}
      {isAdmin && (
        <div className="glass-card">
          <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1.25rem' }}>User Management</h3>
          <UserManager activeSite={activeSite} setActiveSite={setActiveSite} embedded />
        </div>
      )}

      {!isAdmin && (
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1.5rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.875rem', marginBottom: '1.5rem' }}>
          Billing, site, and user management are visible to Admins and Super Admins only.
        </div>
      )}

      {/* About — visible to every role, so support can ask "what version are you on?" */}
      <div className="glass-card" style={{ marginTop: '1.5rem' }}>
        <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '0.75rem' }}>About</h3>
        <AboutPanel />
      </div>
    </div>
  )
}
