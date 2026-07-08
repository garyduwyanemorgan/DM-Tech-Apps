import { useState } from 'react'
import { Menu, Waves } from 'lucide-react'
import { AuthProvider, useAuth } from './context/AuthContext'
import { Login } from './components/Login'
import { Sidebar } from './components/Sidebar'
import { Dashboard } from './components/Dashboard'
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
import { Home } from './components/Home'
import { Settings } from './components/Settings'

const TAB_TITLES: Record<string, string> = {
  home: 'Home',
  dashboard: 'Executive Dashboard',
  upload: 'Log Lab Report',
  simulation: 'Digital Twin',
  compliance: 'Compliance Report',
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
  const { user, loading } = useAuth()
  const [activeTab, setActiveTab] = useState('home')
  const [activeSite, setActiveSite] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [useSampleData, setUseSampleData] = useState<boolean>(() => {
    try { return localStorage.getItem('useSampleData') !== 'false' } catch { return true }
  })

  const handleSampleDataChange = (v: boolean) => {
    setUseSampleData(v)
    try { localStorage.setItem('useSampleData', String(v)) } catch { /* ignore */ }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', flex: 1, minHeight: '100vh', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ opacity: 0.6 }}>Loading...</div>
      </div>
    )
  }

  if (!user) {
    return <Login />
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
          {activeTab === 'dashboard'   && <Dashboard activeSite={activeSite} useSampleData={useSampleData} />}
          {activeTab === 'upload'      && <UploadReport activeSite={activeSite} />}
          {activeTab === 'simulation'  && <ScienceSimulation activeSite={activeSite} />}
          {activeTab === 'compliance'        && <ComplianceReport activeSite={activeSite} />}
          {activeTab === 'monitoring'  && <Monitoring activeSite={activeSite} useSampleData={useSampleData} />}
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
            <Settings
              useSampleData={useSampleData}
              setUseSampleData={handleSampleDataChange}
              activeSite={activeSite}
              setActiveSite={setActiveSite}
            />
          )}
        </main>
      </div>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App
