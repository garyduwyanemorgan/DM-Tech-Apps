import { useState, useEffect, useRef } from 'react'
import { Menu, Waves } from 'lucide-react'
import { AuthProvider, useAuth } from './context/AuthContext'
import { FeaturesProvider, useFeatures, featureForTab } from './context/FeaturesContext'
import { roleMeta } from './lib/roles'
import { Landing } from './components/Landing'
import { Sidebar } from './components/Sidebar'
import { Dashboard } from './components/Dashboard'
import { ProjectDashboard } from './components/dashboards/ProjectDashboard'
import { PortfolioDashboard } from './components/dashboards/PortfolioDashboard'
import { ExecutiveDashboard } from './components/dashboards/ExecutiveDashboard'
import { UploadReport } from './components/UploadReport'
import { ScienceSimulation } from './components/ScienceSimulation'
import { ComplianceReport } from './components/ComplianceReport'
import { Monitoring } from './components/Monitoring'
import { Alerts } from './components/Alerts'
import { Calendar } from './components/Calendar'
import { Sludge } from './components/Sludge'
import { Community } from './components/Community'
import { Drivers } from './components/Drivers'
import { Chemistry } from './components/Chemistry'
import { Ecology } from './components/Ecology'
import { Species } from './components/Species'
import { Technologies } from './components/Technologies'
import { MLSystem } from './components/MLSystem'
import { SiteManager } from './components/SiteManager'
import { UserManager } from './components/UserManager'
import { CorrectiveActions } from './components/CorrectiveActions'
import { Inventory } from './components/Inventory'
import { Assets } from './components/Assets'
import { ManagementKPIs } from './components/ManagementKPIs'
import { Obligations } from './components/Obligations'
import { ModuleCatalogue } from './components/ModuleCatalogue'
import { Home } from './components/Home'
import { Settings } from './components/Settings'

const TAB_TITLES: Record<string, string> = {
  home: 'Home',
  dashboard: 'Executive Dashboard',
  upload: 'Log Lab Report',
  simulation: 'Digital Twin',
  compliance: 'Compliance Report',
  obligations: 'Obligation Registry',
  modules: 'Module Catalogue',
  actions: 'Corrective Actions',
  inventory: 'Inventory & Chemicals',
  assets: 'Assets & Maintenance',
  kpi: 'Management KPIs',
  monitoring: 'Water Quality',
  sludge: 'Sludge Management',
  community: 'Algae & Bloom Forecast',
  alerts: 'Alerts & Response',
  calendar: 'Treatment Calendar',
  drivers: 'Env. Drivers',
  chemistry: 'Chemistry',
  ecology: 'Ecology',
  species: 'Species Matrix',
  technologies: 'Technologies',
  mlsystem: 'ML System',
  sitemanager: 'Site Manager',
  usermanager: 'User Management',
  settings: 'Settings',
}

function AppContent() {
  const { user, loading, role } = useAuth()
  const { features } = useFeatures()
  const [activeTab, setActiveTab] = useState('home')
  const [activeSite, setActiveSite] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Land each role on their dashboard once, after the profile (and thus role)
  // has resolved. Guarded so it never overrides later manual navigation.
  const didInitLanding = useRef(false)
  useEffect(() => {
    if (!loading && user && !didInitLanding.current) {
      didInitLanding.current = true
      setActiveTab('dashboard')
    }
  }, [loading, user])

  // If the page being viewed belongs to a feature that has been switched off
  // in Settings › Features, fall back to Home rather than showing a page the
  // navigation no longer offers.
  useEffect(() => {
    const owner = featureForTab(activeTab)
    if (owner && !features[owner]) setActiveTab('home')
  }, [activeTab, features])

  if (loading) {
    return (
      <div style={{ display: 'flex', flex: 1, minHeight: '100vh', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ opacity: 0.6 }}>Loading...</div>
      </div>
    )
  }

  if (!user) {
    // Public landing page in front of the gate. It renders <Login /> itself once
    // the visitor asks to sign in, so nothing behind authentication changes.
    return <Landing />
  }

  const handleTabChange = (tab: string) => {
    setActiveTab(tab)
    setSidebarOpen(false)
  }

  return (
    <div className="glass-container">
      {/* Mobile overlay — taps outside sidebar to close it */}
      <div
        className={`sidebar-overlay${sidebarOpen ? ' active' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />

      <Sidebar
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        activeSite={activeSite}
        setActiveSite={setActiveSite}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onSitesChanged={() => setSidebarOpen(false)}
      />

      <div className="main-wrapper">
        {/* Mobile-only top bar */}
        <header className="mobile-header">
          <button className="icon-btn" onClick={() => setSidebarOpen(true)} aria-label="Open menu">
            <Menu size={20} />
          </button>
          <div className="mobile-header-title">
            <Waves size={18} color="#6366f1" />
            <span>{TAB_TITLES[activeTab]}</span>
          </div>
          {/* spacer keeps title centred */}
          <div style={{ width: 38 }} />
        </header>

        <main className="main-content">
          {activeTab === 'home'        && <Home activeSite={activeSite} setActiveTab={handleTabChange} />}
          {activeTab === 'dashboard'   && (() => {
            // Role-aware dashboard: each tier sees a different altitude of detail.
            const tier = roleMeta(role).dashboardTier
            if (tier === 4) return <ExecutiveDashboard setActiveSite={setActiveSite} setActiveTab={handleTabChange} />
            if (tier === 3) return <PortfolioDashboard setActiveSite={setActiveSite} setActiveTab={handleTabChange} />
            if (tier === 2) return <ProjectDashboard setActiveSite={setActiveSite} setActiveTab={handleTabChange} />
            return <Dashboard activeSite={activeSite} />
          })()}
          {activeTab === 'upload'      && <UploadReport activeSite={activeSite} />}
          {activeTab === 'simulation'  && <ScienceSimulation activeSite={activeSite} />}
          {activeTab === 'compliance'        && <ComplianceReport activeSite={activeSite} />}
          {activeTab === 'obligations' && <Obligations activeSite={activeSite} />}
          {activeTab === 'modules'     && <ModuleCatalogue />}
          {activeTab === 'actions'     && <CorrectiveActions />}
          {activeTab === 'inventory'   && <Inventory />}
          {activeTab === 'assets'      && <Assets />}
          {activeTab === 'kpi'         && <ManagementKPIs />}
          {activeTab === 'monitoring'  && <Monitoring activeSite={activeSite} />}
          {activeTab === 'sludge'      && <Sludge activeSite={activeSite} />}
          {activeTab === 'community'   && <Community activeSite={activeSite} />}
          {activeTab === 'alerts'      && <Alerts activeSite={activeSite} />}
          {activeTab === 'calendar'    && <Calendar />}
          {activeTab === 'drivers'     && <Drivers />}
          {activeTab === 'chemistry'   && <Chemistry />}
          {activeTab === 'ecology'     && <Ecology />}
          {activeTab === 'species'     && <Species />}
          {activeTab === 'technologies' && <Technologies />}
          {activeTab === 'mlsystem'    && <MLSystem />}
          {activeTab === 'sitemanager' && (
            <SiteManager
              activeSite={activeSite}
              setActiveSite={setActiveSite}
              onSitesChanged={() => {}}
            />
          )}
          {activeTab === 'usermanager' && (
            <UserManager activeSite={activeSite} setActiveSite={setActiveSite} />
          )}
          {activeTab === 'settings' && (
            <Settings activeSite={activeSite} setActiveSite={setActiveSite} />
          )}
        </main>
      </div>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <FeaturesProvider>
        <AppContent />
      </FeaturesProvider>
    </AuthProvider>
  )
}

export default App
