import React, { useEffect, useState } from 'react'
import { Waves } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFeatures, featureForTab } from '../context/FeaturesContext'

interface HomeProps {
  activeSite: string
  setActiveTab: (tab: string) => void
}

export const Home: React.FC<HomeProps> = ({ activeSite, setActiveTab }) => {
  const { organizationId, token, showSampleData } = useAuth()
  const { features } = useFeatures()
  const [siteCount, setSiteCount] = useState<number | null>(null)

  useEffect(() => {
    const fetchCount = async () => {
      try {
        const headers: HeadersInit = {}
        if (token) headers['Authorization'] = `Bearer ${token}`
        if (organizationId) headers['X-Organization-ID'] = organizationId
        const res = await fetch('/api/sites', { headers })
        const data = await res.json()
        setSiteCount((data.sites || []).length)
      } catch {
        setSiteCount(null)
      }
    }
    fetchCount()
  }, [organizationId, token])

  const isLive = !!activeSite

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, minHeight: '100%' }}>

      {/* Hero banner */}
      <div style={{
        background: 'linear-gradient(135deg, #1B3A5C 0%, #2E5D8A 100%)',
        borderRadius: '12px',
        padding: '2.5rem 2rem',
        marginBottom: '1.5rem',
        display: 'flex',
        alignItems: 'center',
        gap: '1.25rem',
      }}>
        <div style={{ background: 'rgba(255,255,255,0.15)', borderRadius: '12px', padding: '0.85rem', display: 'flex', flexShrink: 0 }}>
          <Waves size={36} color="#ffffff" />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.65rem', fontWeight: 800, color: '#ffffff', letterSpacing: '-0.01em', lineHeight: 1.2 }}>
            DUBAI LAGOON MANAGEMENT PLATFORM
          </h1>
          <p style={{ margin: '0.4rem 0 0', color: 'rgba(255,255,255,0.72)', fontSize: '0.9rem' }}>
            Predictive water-quality monitoring &amp; compliance — GDM Enviro Consultants
          </p>
        </div>
      </div>

      {/* Info cards row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginBottom: '1.75rem' }}>
        {/* Lagoons configured */}
        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.1rem 1.25rem' }}>
          <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>
            LAGOONS CONFIGURED
          </div>
          <div style={{ fontSize: '2rem', fontWeight: 800, color: '#1B3A5C', lineHeight: 1 }}>
            {siteCount !== null ? siteCount : '—'}
          </div>
          <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.3rem' }}>Sites in your portfolio</div>
        </div>

        {/* Data source */}
        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.1rem 1.25rem' }}>
          <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>
            DATA SOURCE
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 800, color: isLive ? '#006100' : showSampleData ? '#856404' : '#64748b', lineHeight: 1 }}>
            {isLive ? activeSite : showSampleData ? 'Sample' : 'None'}
          </div>
          <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.3rem' }}>
            {isLive
              ? 'Showing live readings for this site.'
              : showSampleData
              ? 'Showing the demonstration baseline. Select a site for live data.'
              : 'Sample data is off. Select a site with lab readings.'}
          </div>
        </div>

        {/* Compliance standard */}
        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.1rem 1.25rem' }}>
          <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>
            COMPLIANCE STANDARD
          </div>
          <div style={{ fontSize: '1.35rem', fontWeight: 800, color: '#1B3A5C', lineHeight: 1 }}>
            Dubai Municipality (DM)
          </div>
          <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.3rem' }}>Dubai Municipality norms</div>
        </div>
      </div>

      {/* Start here */}
      <div style={{ marginBottom: '1.75rem' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', margin: '0 0 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          Start here
          <span style={{ fontSize: '1rem' }}>↗</span>
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
          {[
            {
              icon: '📋',
              title: 'Record a reading',
              desc: 'Drop a lab report — AI auto-fills the readings.',
              btn: 'Upload Lab Report',
              tab: 'upload',
            },
            {
              icon: '⬆️',
              title: 'Optimise sampling',
              desc: 'See which lagoons to sample and the savings.',
              btn: 'Predictive Monitoring',
              tab: 'simulation',
            },
            {
              icon: '🔍',
              title: 'Diagnose a lagoon',
              desc: 'Why is it at risk, and what to do.',
              btn: 'Lagoon Intelligence',
              tab: 'drivers',
            },
            {
              icon: '📄',
              title: 'Produce a report',
              desc: 'Submission-ready compliance PDF.',
              btn: 'Compliance Reporting',
              tab: 'compliance',
            },
          ].filter(item => {
            // Shortcuts into a feature switched off in Settings › Features are
            // hidden along with the feature's sidebar section.
            const owner = featureForTab(item.tab)
            return !owner || features[owner]
          }).map(item => (
            <div
              key={item.tab}
              style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}
            >
              <div style={{ fontSize: '1.4rem' }}>{item.icon}</div>
              <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1B3A5C' }}>{item.title}</div>
              <div style={{ fontSize: '0.82rem', color: '#64748b', lineHeight: 1.5, flex: 1 }}>{item.desc}</div>
              <button
                onClick={() => setActiveTab(item.tab)}
                style={{
                  marginTop: '0.5rem',
                  background: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '6px',
                  padding: '0.45rem 0.85rem',
                  fontSize: '0.82rem',
                  fontWeight: 600,
                  color: '#1B3A5C',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  textAlign: 'left',
                  transition: 'background 0.15s',
                }}
                onMouseOver={e => (e.currentTarget.style.background = '#D6E4F0')}
                onMouseOut={e => (e.currentTarget.style.background = '#f8fafc')}
              >
                {item.btn} →
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* How the platform works */}
      <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.5rem', marginBottom: '1rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 700, color: '#1B3A5C', margin: '0 0 1rem' }}>How the platform works</h2>
        <ol style={{ margin: 0, padding: '0 0 0 1.2rem', display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
          {[
            { word: 'Record', rest: 'field readings (upload a lab report, or via the field app).' },
            { word: 'Monitor', rest: 'current compliance and alert status across your lagoons.' },
            { word: 'Analyse', rest: '— the intelligence engine forecasts blooms and recommends the cheapest effective intervention.' },
            { word: 'Report', rest: '— generate the official compliance document.' },
            { word: 'Reference', rest: '— treatment calendar, species, sludge and technology guidance.' },
          ].map(({ word, rest }) => (
            <li key={word} style={{ fontSize: '0.875rem', color: '#374151', lineHeight: 1.6 }}>
              <strong style={{ color: '#1B3A5C' }}>{word}</strong> {rest}
            </li>
          ))}
        </ol>
      </div>

      {/* Footer tip */}
      <div style={{ background: '#D6E4F0', border: '1px solid #93c5fd', borderRadius: '8px', padding: '0.75rem 1rem', fontSize: '0.82rem', color: '#1B3A5C' }}>
        Use the sidebar to navigate. Pick your site under <strong>ACTIVE SITE</strong> to switch from sample data to your live readings.
        {' '}Sample data can be turned off for your account in <strong>Settings</strong>.
      </div>
    </div>
  )
}
