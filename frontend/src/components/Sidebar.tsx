import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { LogOut, Settings, Waves, X } from 'lucide-react'

interface SidebarProps {
  activeTab: string
  setActiveTab: (tab: string) => void
  activeSite: string
  setActiveSite: (site: string) => void
  isOpen: boolean
  onClose: () => void
  onSitesChanged?: () => void
}

const DOT_COLORS: Record<string, string> = {
  home: '#60a5fa',
  upload: '#e74c3c',
  dashboard: '#27ae60',
  monitoring: '#27ae60',
  alerts: '#e74c3c',
  drivers: '#6366f1',
  chemistry: '#f59e0b',
  ecology: '#22c55e',
  simulation: '#6366f1',
  compliance: '#2E5D8A',
  calendar: '#64748b',
  sludge: '#64748b',
  technologies: '#64748b',
  species: '#64748b',
  mlsystem: '#64748b',
}

interface NavItem {
  id: string
  label: string
  roles?: string[]
}

const navSections: { label: string; items: NavItem[] }[] = [
  {
    label: 'HOME',
    items: [
      { id: 'home', label: 'Platform Overview' },
    ],
  },
  {
    label: 'DATA ENTRY',
    items: [
      { id: 'upload', label: 'Upload Lab Report', roles: ['super_admin', 'admin', 'operator'] },
    ],
  },
  {
    label: 'MONITORING',
    items: [
      { id: 'dashboard',  label: 'Executive Dashboard' },
      { id: 'monitoring', label: 'Water Quality Monitoring' },
      { id: 'sludge',     label: 'Sludge & Sediment Mgmt' },
      { id: 'community',  label: 'Algae & Bloom Forecast' },
      { id: 'alerts',     label: 'Alert & Response Protocol' },
    ],
  },
  {
    label: 'REPORTING',
    items: [
      { id: 'compliance', label: 'Compliance Reporting' },
    ],
  },
  {
    label: 'INTELLIGENCE',
    items: [
      { id: 'drivers',    label: 'Environmental Drivers' },
      { id: 'chemistry',  label: 'Chemistry Loop' },
      { id: 'ecology',    label: 'Ecology Loop' },
      { id: 'simulation', label: 'Digital Twin Simulator' },
    ],
  },
  {
    label: 'REFERENCE',
    items: [
      { id: 'calendar',     label: 'Seasonal Treatment Calendar' },
      { id: 'technologies', label: 'Intervention Technologies' },
      { id: 'species',      label: 'Species Threat Matrix' },
      { id: 'mlsystem',     label: 'ML Prediction System' },
    ],
  },
]

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  activeSite,
  setActiveSite,
  isOpen,
  onClose,
  onSitesChanged: _onSitesChanged,
}) => {
  const { signOut, role, organizationId } = useAuth()
  const [sites, setSites] = useState<string[]>([])
  const [siteDropdownOpen, setSiteDropdownOpen] = useState(false)

  useEffect(() => {
    if (organizationId) fetchSites()
  }, [organizationId])

  const fetchSites = async () => {
    try {
      const headers: HeadersInit = {}
      if (organizationId) headers['X-Organization-ID'] = organizationId
      const res = await fetch('/api/sites', { headers })
      const data = await res.json()
      if (data.sites) {
        // API returns [{name, reading_count}] — normalise to string[]
        const names: string[] = data.sites.map((s: any) => (typeof s === 'string' ? s : s.name))
        setSites(names)
        if (names.length > 0 && !activeSite) setActiveSite(names[0])
      }
    } catch (err) {
      console.error('Failed to fetch sites:', err)
    }
  }

  const sectionLabelStyle: React.CSSProperties = {
    fontSize: '0.65rem',
    fontWeight: 700,
    color: 'rgba(255,255,255,0.4)',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    padding: '0.5rem 0.5rem 0.3rem',
  }

  const navItemStyle = (id: string): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    gap: '0.65rem',
    padding: '0.45rem 0.75rem',
    borderRadius: '6px',
    cursor: 'pointer',
    background: activeTab === id ? 'rgba(255,255,255,0.12)' : 'transparent',
    border: 'none',
    width: '100%',
    textAlign: 'left',
    fontSize: '0.875rem',
    fontWeight: activeTab === id ? 600 : 400,
    color: activeTab === id ? '#ffffff' : 'rgba(255,255,255,0.72)',
    transition: 'background 0.15s, color 0.15s',
    fontFamily: 'inherit',
  })

  return (
    <div className={`sidebar${isOpen ? ' sidebar-open' : ''}`}>
      {/* Branding */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <Waves size={24} color="#60a5fa" />
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#ffffff', lineHeight: 1.2 }}>Dubai Lagoons</div>
            <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.55)' }}>Management Dashboard</div>
          </div>
        </div>
        <button
          className="sidebar-close-btn"
          onClick={onClose}
          style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.6)', cursor: 'pointer', padding: 4 }}
          aria-label="Close menu"
        >
          <X size={18} />
        </button>
      </div>

      {/* Active site selector */}
      <div style={{ marginTop: '1.25rem', marginBottom: '0.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
          <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            ACTIVE SITE
          </span>
          <button
            title="Manage Sites"
            onClick={() => { setActiveTab('sitemanager'); onClose() }}
            style={{ background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: 4, color: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: '0.7rem', fontWeight: 700, lineHeight: 1, padding: '2px 7px', fontFamily: 'inherit' }}
          >
            + Manage
          </button>
        </div>
        {/* Custom dropdown — native <select> ignores CSS on Windows */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setSiteDropdownOpen(v => !v)}
            style={{
              width: '100%',
              background: 'rgba(255,255,255,0.12)',
              border: '1px solid rgba(255,255,255,0.25)',
              borderRadius: '6px',
              padding: '0.45rem 0.75rem',
              color: '#ffffff',
              fontSize: '0.875rem',
              fontFamily: 'inherit',
              cursor: 'pointer',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              textAlign: 'left',
            }}
          >
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {activeSite || '— no site selected —'}
            </span>
            <span style={{ marginLeft: '0.5rem', opacity: 0.6, fontSize: '0.65rem', flexShrink: 0 }}>
              {siteDropdownOpen ? '▲' : '▼'}
            </span>
          </button>

          {siteDropdownOpen && sites.length > 0 && (
            <div style={{
              position: 'absolute',
              top: 'calc(100% + 3px)',
              left: 0,
              right: 0,
              zIndex: 200,
              background: '#162e4a',
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '6px',
              boxShadow: '0 6px 20px rgba(0,0,0,0.5)',
              maxHeight: '180px',
              overflowY: 'auto',
            }}>
              {sites.map((s) => (
                <button
                  key={s}
                  onClick={() => { setActiveSite(s); setSiteDropdownOpen(false) }}
                  style={{
                    width: '100%',
                    background: s === activeSite ? 'rgba(255,255,255,0.15)' : 'transparent',
                    border: 'none',
                    borderRadius: 0,
                    color: s === activeSite ? '#ffffff' : 'rgba(255,255,255,0.8)',
                    padding: '0.5rem 0.75rem',
                    textAlign: 'left',
                    cursor: 'pointer',
                    fontSize: '0.875rem',
                    fontFamily: 'inherit',
                    display: 'block',
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.45)', marginTop: '0.3rem', paddingLeft: '2px' }}>
          {sites.length === 0 ? 'Showing sample data' : `${sites.length} site${sites.length > 1 ? 's' : ''} available`}
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, overflowY: 'auto', marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.1rem' }}>
        {navSections.map((section) => {
          const visibleItems = section.items.filter(
            (item) => !item.roles || item.roles.includes(role)
          )
          if (visibleItems.length === 0) return null
          return (
            <div key={section.label} style={{ marginBottom: '0.5rem' }}>
              <div style={sectionLabelStyle}>{section.label}</div>
              {visibleItems.map((item) => {
                const isActive = activeTab === item.id
                const dotColor = DOT_COLORS[item.id] ?? '#64748b'
                return (
                  <button
                    key={item.id}
                    style={navItemStyle(item.id)}
                    onClick={() => { setActiveTab(item.id); onClose() }}
                  >
                    {/* Dot indicator */}
                    <span style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      flexShrink: 0,
                      background: isActive ? dotColor : 'transparent',
                      border: `1.5px solid ${isActive ? dotColor : 'rgba(255,255,255,0.35)'}`,
                      display: 'inline-block',
                    }} />
                    {item.label}
                  </button>
                )
              })}
            </div>
          )
        })}
      </nav>

      {/* Bottom controls */}
      <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
        {/* Settings */}
        <button
          onClick={() => { setActiveTab('settings'); onClose() }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.65rem',
            padding: '0.45rem 0.75rem',
            borderRadius: '6px',
            cursor: 'pointer',
            background: activeTab === 'settings' ? 'rgba(255,255,255,0.12)' : 'transparent',
            border: 'none',
            width: '100%',
            color: activeTab === 'settings' ? '#ffffff' : 'rgba(255,255,255,0.72)',
            fontSize: '0.875rem',
            fontWeight: activeTab === 'settings' ? 600 : 400,
            fontFamily: 'inherit',
            marginBottom: '0.1rem',
          }}
        >
          <Settings size={16} />
          Settings
        </button>

        {/* Sign out */}
        <button
          onClick={signOut}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.65rem',
            padding: '0.45rem 0.75rem',
            borderRadius: '6px',
            cursor: 'pointer',
            background: 'transparent',
            border: 'none',
            width: '100%',
            color: 'rgba(255,255,255,0.6)',
            fontSize: '0.875rem',
            fontFamily: 'inherit',
          }}
        >
          <LogOut size={16} />
          Sign Out
        </button>

        {/* Footer */}
        <div style={{ marginTop: '1rem', fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', lineHeight: 1.6, textAlign: 'center' }}>
          GDM Enviro Consultants<br />
          Compliance Reporting — Dubai Lands<br />
          © 2026
        </div>
      </div>
    </div>
  )
}
