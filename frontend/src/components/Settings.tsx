import React, { useEffect, useState } from 'react'
import { Tab, TabList, TabPanel, Tabs, type Key } from 'react-aria-components'
import { useAuth } from '../context/AuthContext'
import { PageHeader } from './PageHeader'
import { SiteManager } from './SiteManager'
import { UserManager } from './UserManager'
import { SampleDataToggle } from './SampleDataToggle'
import { hasPermission } from '../lib/permissions'
import { COLORS } from '../lib/tokens'

interface SettingsProps {
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

interface DemoStatus {
  exists: boolean
  active: boolean
  expired: boolean
  days_left: number
  activated_at: string | null
  expires_at: string | null
  has_subscription: boolean
  can_activate: boolean
}

const DEMO_EXPLAINER =
  'Demo mode unlocks the full system for one month — unlimited sites, all features — so you ' +
  'can test end-to-end: add your real sites, invite your team, upload readings. When the month ' +
  'ends the system becomes read-only until you choose a plan; everything you set up carries ' +
  'over to your live system. One demo per organisation.'

const DemoPanel: React.FC<{ organizationId: string | null; token: string | null; role: string | null }> = ({ organizationId, token, role }) => {
  const [status, setStatus] = useState<DemoStatus | null>(null)
  const [activating, setActivating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const headers = (): HeadersInit => {
    const h: HeadersInit = { 'Content-Type': 'application/json' }
    if (token) h['Authorization'] = `Bearer ${token}`
    if (organizationId) h['X-Organization-ID'] = organizationId
    return h
  }

  const loadStatus = async () => {
    try {
      const res = await fetch('/api/demo/status', { headers: headers() })
      if (res.ok) setStatus(await res.json())
    } catch { /* panel simply stays hidden */ }
  }

  useEffect(() => { loadStatus() }, [organizationId])

  const handleActivate = async () => {
    setActivating(true)
    setError(null)
    try {
      const res = await fetch('/api/demo/activate', { method: 'POST', headers: headers() })
      const data = await res.json()
      if (!res.ok) { setError(data.detail || 'Could not activate the demo.'); return }
      await loadStatus()
    } catch { setError('Network error. Try again.') }
    finally { setActivating(false) }
  }

  // Live orgs don't need the demo panel; hide until the status has loaded too.
  if (!status || status.has_subscription) return null
  const mayActivate = hasPermission(role, 'demo.activate')

  return (
    <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
      <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1rem' }}>Demo Mode</h3>

      {error && (
        <div style={{ background: '#FFC7CE', color: '#9C0006', padding: '0.75rem 1rem', borderRadius: 6, fontSize: '0.875rem', marginBottom: '1rem' }}>
          {error}
        </div>
      )}

      {!status.exists ? (
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <p style={{ flex: '1 1 320px', margin: 0, fontSize: '0.85rem', color: '#64748b', lineHeight: 1.6 }}>
            {DEMO_EXPLAINER}
          </p>
          {mayActivate ? (
            <button
              onClick={handleActivate}
              disabled={activating}
              title={DEMO_EXPLAINER}
              style={{ padding: '0.55rem 1.25rem', fontSize: '0.9rem', fontWeight: 600 }}
            >
              {activating ? 'Activating…' : '🚀 Activate Demo — 1 Month'}
            </button>
          ) : (
            <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              Only Executive Management can activate the demo.
            </span>
          )}
        </div>
      ) : status.active ? (
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{
            background: '#D6E4F0', color: '#1B3A5C', border: '1px solid #93c5fd',
            borderRadius: 10, padding: '0.75rem 1.25rem', fontWeight: 700, fontSize: '1.05rem',
            display: 'flex', alignItems: 'baseline', gap: '0.4rem',
          }}>
            <span style={{ fontSize: '1.5rem' }}>{status.days_left}</span>
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>day{status.days_left === 1 ? '' : 's'} left</span>
          </div>
          <p style={{ flex: '1 1 280px', margin: 0, fontSize: '0.82rem', color: '#64748b', lineHeight: 1.6 }}>
            Demo is active — unlimited sites, all features.
            {status.expires_at && <> Ends {new Date(status.expires_at).toLocaleDateString()}.</>}{' '}
            Switch to live any time by choosing a plan below; everything carries over.
          </p>
        </div>
      ) : (
        <div style={{ background: '#FFEB9C', color: '#856404', border: '1px solid #fcd34d', borderRadius: 8, padding: '0.85rem 1rem', fontSize: '0.85rem', lineHeight: 1.6 }}>
          <strong>Your demo has ended</strong> — the system is now read-only. Choose a plan under
          Subscription &amp; Billing to switch to live; everything you set up during the demo carries over.
        </div>
      )}
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

const SETTINGS_TAB_KEY = 'settingsActiveTab'

// Untitled UI settings-page pattern (settings-01): the page header, a single
// horizontal row of tab labels, and ONE section per tab — no scrolling up and
// down a long page hunting for the right card.
export const Settings: React.FC<SettingsProps> = ({ activeSite, setActiveSite }) => {
  const { role, organizationId, token } = useAuth()
  const isAdmin = role === 'admin' || role === 'super_admin'

  const tabs: { id: string; label: string }[] = [
    ...(isAdmin ? [{ id: 'billing', label: 'Plan & Billing' }] : []),
    { id: 'display', label: 'Data & Display' },
    ...(isAdmin ? [
      { id: 'sites', label: 'Site Management' },
      { id: 'users', label: 'User Management' },
    ] : []),
    { id: 'about', label: 'About' },
  ]

  const [tab, setTab] = useState<string>(() => {
    try {
      const saved = localStorage.getItem(SETTINGS_TAB_KEY)
      if (saved && tabs.some(t => t.id === saved)) return saved
    } catch { /* ignore */ }
    return tabs[0].id
  })

  const handleTab = (key: Key) => {
    const id = String(key)
    setTab(id)
    try { localStorage.setItem(SETTINGS_TAB_KEY, id) } catch { /* ignore */ }
  }

  const tabStyle = ({ isSelected, isFocusVisible }: { isSelected: boolean; isFocusVisible: boolean }): React.CSSProperties => ({
    padding: '0.65rem 0.25rem',
    marginBottom: -1,
    fontSize: '0.9rem',
    fontWeight: 600,
    fontFamily: 'inherit',
    color: isSelected ? COLORS.accent : COLORS.slate,
    borderBottom: `2px solid ${isSelected ? COLORS.accent : 'transparent'}`,
    cursor: 'pointer',
    outline: isFocusVisible ? `2px solid ${COLORS.accent}` : 'none',
    outlineOffset: 2,
    whiteSpace: 'nowrap',
    transition: 'color 0.15s, border-color 0.15s',
  })

  const panelStyle: React.CSSProperties = { paddingTop: '1.5rem', outline: 'none' }

  return (
    <div style={{ maxWidth: 960 }}>
      <PageHeader title="Settings" subtitle="Platform configuration, billing, and administration" icon="⚙️" />

      <Tabs selectedKey={tab} onSelectionChange={handleTab}>
        <TabList
          aria-label="Settings sections"
          style={{
            display: 'flex', gap: '1.5rem', borderBottom: `1px solid ${COLORS.border}`,
            overflowX: 'auto', paddingBottom: 0,
          }}
        >
          {tabs.map(t => <Tab key={t.id} id={t.id} style={tabStyle}>{t.label}</Tab>)}
        </TabList>

        {isAdmin && (
          <TabPanel id="billing" style={panelStyle}>
            <DemoPanel organizationId={organizationId} token={token} role={role} />
            <div className="glass-card">
              <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1.25rem' }}>
                Subscription &amp; Billing
              </h3>
              <BillingPanel organizationId={organizationId} token={token} />
            </div>
          </TabPanel>
        )}

        <TabPanel id="display" style={panelStyle}>
          {/* Visible to every role, including Executive Management and the
              General Manager. Same switch as the one on their dashboards. */}
          <div className="glass-card">
            <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1rem' }}>Data &amp; Display</h3>
            <SampleDataToggle variant="card" />
          </div>
          {!isAdmin && (
            <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1rem', textAlign: 'center', color: '#94a3b8', fontSize: '0.875rem', marginTop: '1.5rem' }}>
              Billing, site, and user management are visible to Admins and Super Admins only.
            </div>
          )}
        </TabPanel>

        {isAdmin && (
          <TabPanel id="sites" style={panelStyle}>
            <div className="glass-card">
              <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1.25rem' }}>Site Management</h3>
              <SiteManager activeSite={activeSite} setActiveSite={setActiveSite} onSitesChanged={() => {}} embedded />
            </div>
          </TabPanel>
        )}

        {isAdmin && (
          <TabPanel id="users" style={panelStyle}>
            <div className="glass-card">
              <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '1.25rem' }}>User Management</h3>
              <UserManager activeSite={activeSite} setActiveSite={setActiveSite} embedded />
            </div>
          </TabPanel>
        )}

        <TabPanel id="about" style={panelStyle}>
          {/* Visible to every role, so support can ask "what version are you on?" */}
          <div className="glass-card">
            <h3 className="section-heading" style={{ marginTop: 0, marginBottom: '0.75rem' }}>About</h3>
            <AboutPanel />
          </div>
        </TabPanel>
      </Tabs>
    </div>
  )
}
