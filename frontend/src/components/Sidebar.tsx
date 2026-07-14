// App sidebar — ERP-style navigation (reference: Downloads/WIP/2.jpg).
//
//   - Collapsible sub-menu groups with icons + rotating chevrons
//   - Active item = solid accent highlight (design-system Accent token)
//   - Whole sidebar collapses to a 68px icon rail via the header button;
//     clicking a group icon while collapsed re-expands and opens that group
//   - Signed-in user (initials avatar + name + role badge) pinned at bottom
//
// Expanded-groups and collapsed state persist in localStorage. The mobile
// overlay behaviour (.sidebar-open, ≤768px) is unchanged.
import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  LogOut, Settings, Waves, X, ChevronDown, PanelLeftClose, PanelLeftOpen,
  Home, FileUp, Activity, Wrench, FileText, FlaskConical, BookOpen,
  type LucideIcon,
} from 'lucide-react'
import { RoleBadge } from './RoleBadge'
import { COLORS } from '../lib/tokens'
import { hasPermission, type Permission } from '../lib/permissions'

interface SidebarProps {
  activeTab: string
  setActiveTab: (tab: string) => void
  activeSite: string
  setActiveSite: (site: string) => void
  isOpen: boolean
  onClose: () => void
  onSitesChanged?: () => void
}

interface NavItem {
  id: string
  label: string
  roles?: string[]
  /** Atomic permission gate (usability only; backend enforces authorization). */
  permission?: Permission
}

interface NavEntry {
  /** Single item (navigates directly) or group (expands to children). */
  icon: LucideIcon
  label: string
  /** Present on singles only. */
  id?: string
  roles?: string[]
  permission?: Permission
  /** Present on groups only. */
  children?: NavItem[]
}

const NAV: NavEntry[] = [
  { icon: Home, label: 'Platform Overview', id: 'home' },
  { icon: FileUp, label: 'Upload Lab Report', id: 'upload', roles: ['super_admin', 'admin', 'operator'] },
  {
    icon: Activity, label: 'Monitoring',
    children: [
      { id: 'dashboard',  label: 'Executive Dashboard' },
      { id: 'monitoring', label: 'Water Quality Monitoring' },
      { id: 'sludge',     label: 'Sludge & Sediment Mgmt' },
      { id: 'community',  label: 'Algae & Bloom Forecast' },
      { id: 'alerts',     label: 'Alert & Response Protocol' },
    ],
  },
  {
    icon: Wrench, label: 'Operations',
    children: [
      { id: 'actions',   label: 'Corrective Actions', permission: 'actions.read' },
      { id: 'inventory', label: 'Inventory & Chemicals', permission: 'inventory.read' },
      { id: 'assets',    label: 'Assets & Maintenance', permission: 'assets.read' },
    ],
  },
  {
    icon: FileText, label: 'Reporting',
    children: [
      { id: 'compliance', label: 'Compliance Reporting' },
      { id: 'kpi',        label: 'Management KPIs', permission: 'analytics.portfolio.read' },
    ],
  },
  {
    icon: FlaskConical, label: 'Intelligence',
    children: [
      { id: 'drivers',    label: 'Environmental Drivers' },
      { id: 'chemistry',  label: 'Chemistry Loop' },
      { id: 'ecology',    label: 'Ecology Loop' },
      { id: 'simulation', label: 'Digital Twin Simulator' },
    ],
  },
  {
    icon: BookOpen, label: 'Reference',
    children: [
      { id: 'calendar',     label: 'Seasonal Treatment Calendar' },
      { id: 'technologies', label: 'Intervention Technologies' },
      { id: 'species',      label: 'Species Threat Matrix' },
      { id: 'mlsystem',     label: 'ML Prediction System' },
    ],
  },
]

const EXPANDED_KEY = 'sidebarExpandedGroups'
const COLLAPSED_KEY = 'sidebarCollapsed'

const initials = (name: string, email: string): string => {
  const src = name.trim() || email
  const words = src.split(/\s+/).filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return src.slice(0, 2).toUpperCase()
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  activeSite,
  setActiveSite,
  isOpen,
  onClose,
  onSitesChanged: _onSitesChanged,
}) => {
  const { signOut, role, organizationId, user } = useAuth()
  const [sites, setSites] = useState<string[]>([])
  const [siteDropdownOpen, setSiteDropdownOpen] = useState(false)
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem(COLLAPSED_KEY) === 'true' } catch { return false }
  })
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem(EXPANDED_KEY) || '{}') } catch { return {} }
  })

  useEffect(() => {
    if (organizationId) fetchSites()
  }, [organizationId])

  // The group holding the active tab always stays visible.
  useEffect(() => {
    const owner = NAV.find(e => e.children?.some(c => c.id === activeTab))
    if (owner && !expanded[owner.label]) {
      setExpandedPersist({ ...expanded, [owner.label]: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab])

  const setExpandedPersist = (next: Record<string, boolean>) => {
    setExpanded(next)
    try { localStorage.setItem(EXPANDED_KEY, JSON.stringify(next)) } catch { /* ignore */ }
  }

  const setCollapsedPersist = (value: boolean) => {
    setCollapsed(value)
    try { localStorage.setItem(COLLAPSED_KEY, String(value)) } catch { /* ignore */ }
  }

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

  const visible = (item: { roles?: string[]; permission?: Permission }): boolean =>
    (!item.roles || item.roles.includes(role)) &&
    (!item.permission || hasPermission(role, item.permission))

  const navigate = (id: string) => { setActiveTab(id); onClose() }

  const toggleGroup = (label: string) => {
    if (collapsed) {
      // Re-expand the rail and open this group.
      setCollapsedPersist(false)
      setExpandedPersist({ ...expanded, [label]: true })
      return
    }
    setExpandedPersist({ ...expanded, [label]: !expanded[label] })
  }

  const rowBase: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '0.65rem',
    padding: collapsed ? '0.55rem 0' : '0.5rem 0.75rem',
    justifyContent: collapsed ? 'center' : 'flex-start',
    borderRadius: '8px',
    cursor: 'pointer',
    border: 'none',
    width: '100%',
    textAlign: 'left',
    fontSize: '0.875rem',
    transition: 'background 0.15s, color 0.15s',
    fontFamily: 'inherit',
    background: 'transparent',
    color: 'rgba(255,255,255,0.72)',
  }

  const activeRow: React.CSSProperties = {
    background: COLORS.accent,
    color: '#ffffff',
    fontWeight: 600,
  }

  const displayName = user?.name || user?.email || ''

  return (
    <div className={`sidebar${isOpen ? ' sidebar-open' : ''}${collapsed ? ' sidebar-collapsed' : ''}`}>
      {/* Branding + collapse control */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'space-between', marginBottom: '0.5rem' }}>
        {!collapsed && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <Waves size={24} color="#60a5fa" />
            <div>
              <div style={{ fontSize: '1rem', fontWeight: 700, color: '#ffffff', lineHeight: 1.2 }}>Dubai Lagoons</div>
              <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.55)' }}>Management Dashboard</div>
            </div>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <button
            className="sidebar-collapse-btn"
            onClick={() => setCollapsedPersist(!collapsed)}
            style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.6)', cursor: 'pointer', padding: 4 }}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <button
            className="sidebar-close-btn"
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.6)', cursor: 'pointer', padding: 4 }}
            aria-label="Close menu"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Active site selector (hidden on the icon rail) */}
      {!collapsed && (
        <div style={{ marginTop: '1rem', marginBottom: '0.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
            <span style={{ fontSize: '0.65rem', fontWeight: 700, color: 'rgba(255,255,255,0.4)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              ACTIVE SITE
            </span>
            <button
              title="Manage Sites"
              onClick={() => navigate('sitemanager')}
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
      )}

      {/* Navigation */}
      <nav style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', marginTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
        {NAV.map((entry) => {
          const Icon = entry.icon

          // Single item
          if (entry.id) {
            if (!visible(entry)) return null
            const isActive = activeTab === entry.id
            return (
              <button
                key={entry.id}
                onClick={() => navigate(entry.id!)}
                title={collapsed ? entry.label : undefined}
                style={{ ...rowBase, ...(isActive ? activeRow : {}) }}
              >
                <Icon size={17} style={{ flexShrink: 0 }} />
                {!collapsed && entry.label}
              </button>
            )
          }

          // Group
          const children = (entry.children ?? []).filter(visible)
          if (children.length === 0) return null
          const isOpenGroup = !!expanded[entry.label] && !collapsed
          const hasActiveChild = children.some(c => c.id === activeTab)

          return (
            <div key={entry.label}>
              <button
                onClick={() => toggleGroup(entry.label)}
                title={collapsed ? entry.label : undefined}
                style={{
                  ...rowBase,
                  // Collapsed rail: a group whose child is active gets the accent chip.
                  ...(collapsed && hasActiveChild ? activeRow : {}),
                  ...(!collapsed && hasActiveChild && !isOpenGroup ? { color: '#ffffff', fontWeight: 600 } : {}),
                }}
              >
                <Icon size={17} style={{ flexShrink: 0 }} />
                {!collapsed && (
                  <>
                    <span style={{ flex: 1 }}>{entry.label}</span>
                    <ChevronDown
                      size={15}
                      style={{
                        flexShrink: 0,
                        opacity: 0.55,
                        transform: isOpenGroup ? 'rotate(180deg)' : 'none',
                        transition: 'transform 0.15s',
                      }}
                    />
                  </>
                )}
              </button>

              {isOpenGroup && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem', margin: '0.1rem 0 0.25rem' }}>
                  {children.map((item) => {
                    const isActive = activeTab === item.id
                    return (
                      <button
                        key={item.id}
                        onClick={() => navigate(item.id)}
                        style={{
                          ...rowBase,
                          padding: '0.4rem 0.75rem 0.4rem 2.45rem',
                          fontSize: '0.84rem',
                          ...(isActive ? activeRow : {}),
                        }}
                      >
                        {item.label}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>

      {/* Bottom controls */}
      <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
        {/* Settings */}
        <button
          onClick={() => navigate('settings')}
          title={collapsed ? 'Settings' : undefined}
          style={{ ...rowBase, ...(activeTab === 'settings' ? activeRow : {}), marginBottom: '0.1rem' }}
        >
          <Settings size={16} style={{ flexShrink: 0 }} />
          {!collapsed && 'Settings'}
        </button>

        {/* Sign out */}
        <button
          onClick={signOut}
          title={collapsed ? 'Sign Out' : undefined}
          style={{ ...rowBase, color: 'rgba(255,255,255,0.6)' }}
        >
          <LogOut size={16} style={{ flexShrink: 0 }} />
          {!collapsed && 'Sign Out'}
        </button>

        {/* Signed-in user */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          gap: '0.65rem',
          padding: collapsed ? '0.75rem 0 0.25rem' : '0.75rem 0.35rem 0.25rem',
          marginTop: '0.5rem',
          borderTop: '1px solid rgba(255,255,255,0.1)',
        }}>
          <div
            title={displayName}
            style={{
              width: 34,
              height: 34,
              borderRadius: '50%',
              background: COLORS.accent,
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '0.78rem',
              fontWeight: 700,
              flexShrink: 0,
              letterSpacing: '0.02em',
            }}
          >
            {initials(user?.name ?? '', user?.email ?? '')}
          </div>
          {!collapsed && (
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#ffffff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {displayName}
              </div>
              <div style={{ marginTop: 3 }}>
                <RoleBadge role={role} onDark size="sm" />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        {!collapsed && (
          <div style={{ marginTop: '0.75rem', fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)', lineHeight: 1.6, textAlign: 'center' }}>
            GDM Enviro Consultants<br />
            Compliance Reporting — Dubai Lands<br />
            © 2026
          </div>
        )}
      </div>
    </div>
  )
}
