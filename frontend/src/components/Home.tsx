import React, { useEffect, useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useFeatures, featureForTab } from '../context/FeaturesContext'

interface HomeProps {
  activeSite: string
  setActiveTab: (tab: string) => void
}

// A count on a compliance dashboard is load-bearing: "0 assets configured" and
// "we could not ask the server" mean very different things to the person reading
// it, so the two states are tracked separately and never collapse into a 0.
type CountState = 'loading' | 'ready' | 'unavailable'

export const Home: React.FC<HomeProps> = ({ activeSite, setActiveTab }) => {
  const { organizationId, token, showSampleData } = useAuth()
  const { features } = useFeatures()
  const [assetCount, setAssetCount] = useState<number | null>(null)
  const [countState, setCountState] = useState<CountState>('loading')

  useEffect(() => {
    let cancelled = false

    const fetchAssets = async () => {
      setCountState('loading')
      try {
        const headers: HeadersInit = {}
        if (token) headers['Authorization'] = `Bearer ${token}`
        if (organizationId) headers['X-Organization-ID'] = organizationId

        // `activeSite` is the site NAME; /api/assets filters on the site id, so
        // resolve one to the other first. If the site cannot be resolved we fall
        // back to the whole organisation rather than reporting a wrong number.
        let url = '/api/assets'
        if (activeSite) {
          const sitesRes = await fetch('/api/sites', { headers })
          if (!sitesRes.ok) throw new Error(`sites ${sitesRes.status}`)
          const sitesData = await sitesRes.json()
          const match = (sitesData.sites || []).find(
            (s: any) => (typeof s === 'string' ? s : s?.name) === activeSite
          )
          const siteId = match && typeof match !== 'string' ? match.id : undefined
          if (siteId) url = `/api/assets?site_id=${encodeURIComponent(siteId)}`
        }

        const res = await fetch(url, { headers })
        if (!res.ok) throw new Error(`assets ${res.status}`)
        const data = await res.json()
        if (!Array.isArray(data?.assets)) throw new Error('unexpected response')
        if (cancelled) return
        setAssetCount(data.assets.length)
        setCountState('ready')
      } catch {
        if (cancelled) return
        setAssetCount(null)
        setCountState('unavailable')
      }
    }

    fetchAssets()
    return () => { cancelled = true }
  }, [organizationId, token, activeSite])

  const scopeLabel = activeSite || 'your organisation'

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
          <ShieldCheck size={36} color="#ffffff" />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.65rem', fontWeight: 800, color: '#ffffff', letterSpacing: '-0.01em', lineHeight: 1.2 }}>
            COMPLIANCE INTELLIGENCE PLATFORM
          </h1>
          <p style={{ margin: '0.4rem 0 0', color: 'rgba(255,255,255,0.72)', fontSize: '0.9rem' }}>
            Laboratory certificates, asset compliance &amp; audit-ready reporting for facilities management — GDM Enviro Consultants
          </p>
        </div>
      </div>

      {/* Info cards row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginBottom: '1.75rem' }}>
        {/* Assets configured — the configured setup for the selected site. Assets
            are what laboratory certificates attach to, so this is the number that
            tells you whether the site is ready to be reported on. */}
        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: '10px', padding: '1.1rem 1.25rem' }}>
          <div style={{ fontSize: '0.68rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.4rem' }}>
            ASSETS CONFIGURED
          </div>
          <div
            style={{
              fontSize: countState === 'ready' && assetCount ? '2rem' : '1.35rem',
              fontWeight: 800,
              color: countState === 'unavailable' ? '#94a3b8' : '#1B3A5C',
              lineHeight: 1,
            }}
            aria-live="polite"
          >
            {countState === 'loading' && '—'}
            {countState === 'unavailable' && 'Unavailable'}
            {countState === 'ready' && (assetCount ? assetCount : 'None yet')}
          </div>
          <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '0.3rem' }}>
            {countState === 'loading' && `Checking the setup for ${scopeLabel}…`}
            {countState === 'unavailable' && 'Count could not be read — no number is shown rather than a wrong one.'}
            {countState === 'ready' && (assetCount
              ? `Configured for ${scopeLabel}`
              : `No assets are configured for ${scopeLabel} yet. Add them in Site Manager so certificates have something to attach to.`)}
          </div>
          {countState === 'ready' && !assetCount && (
            <button
              onClick={() => setActiveTab('sitemanager')}
              style={{
                marginTop: '0.6rem',
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '6px',
                padding: '0.35rem 0.7rem',
                fontSize: '0.78rem',
                fontWeight: 600,
                color: '#1B3A5C',
                cursor: 'pointer',
                fontFamily: 'inherit',
                transition: 'background 0.15s',
              }}
              onMouseOver={e => (e.currentTarget.style.background = '#D6E4F0')}
              onMouseOut={e => (e.currentTarget.style.background = '#f8fafc')}
            >
              Open Site Manager →
            </button>
          )}
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
              title: 'File a certificate',
              desc: 'Upload a lab certificate and confirm the readings against the asset it belongs to.',
              btn: 'Upload Lab Report',
              tab: 'upload',
            },
            {
              icon: '⬆️',
              title: 'Plan your sampling',
              desc: 'See which assets are due for sampling before the next submission.',
              btn: 'Digital Twin Simulator',
              tab: 'simulation',
            },
            {
              icon: '🔍',
              title: 'Investigate a result',
              desc: 'What is driving an out-of-specification asset, and what to do about it.',
              btn: 'Environmental Drivers',
              tab: 'drivers',
            },
            {
              icon: '📄',
              title: 'Produce a report',
              desc: 'Submission-ready compliance PDF for the site.',
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
            { word: 'Configure', rest: 'each site and the assets on it — water bodies, tanks, fountains, outlets and equipment. Certificates attach to assets.' },
            { word: 'Upload', rest: 'the laboratory certificate for an asset; the results are read from the PDF for you.' },
            { word: 'Confirm', rest: 'the extracted results before they are filed — nothing enters the compliance record unreviewed.' },
            { word: 'Report', rest: '— confirmed results feed the compliance status and the submission-ready document for the site.' },
            { word: 'Oversee', rest: '— management KPIs roll the same record up across every site in the portfolio.' },
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
