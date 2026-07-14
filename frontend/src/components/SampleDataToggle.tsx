/**
 * The sample/demo data switch.
 *
 * Lives in Settings (all roles) and is surfaced inline on the Executive and Portfolio
 * dashboards, because Executive Management and the General Manager land there and need
 * to be able to take demonstration figures off their portfolio view without hunting
 * through Settings.
 *
 * The preference is stored on the user's profile, so flipping it here or in Settings is
 * the same switch, and it follows the user across devices.
 */
import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { Switch } from './ui/Toggle'

// Re-exported for existing importers; the component itself now lives in ui/Toggle.
export { Switch }

/**
 * `variant="card"` — the full Settings block with an explanation.
 * `variant="inline"` — a compact strip for the top of a dashboard.
 */
export const SampleDataToggle: React.FC<{ variant?: 'card' | 'inline' }> = ({
  variant = 'card',
}) => {
  const { showSampleData, setShowSampleData } = useAuth()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handle = async (value: boolean) => {
    setSaving(true)
    setError(null)
    try {
      await setShowSampleData(value)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save preference')
    } finally {
      setSaving(false)
    }
  }

  if (variant === 'inline') {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: '1rem', flexWrap: 'wrap',
        padding: '0.65rem 1rem',
        background: showSampleData ? '#FFEB9C' : '#f8fafc',
        border: `1px solid ${showSampleData ? '#fcd34d' : '#e2e8f0'}`,
        borderRadius: 8,
      }}>
        <div style={{ fontSize: '0.85rem', color: showSampleData ? '#856404' : '#64748b', lineHeight: 1.5 }}>
          {showSampleData ? (
            <>
              <strong>Sample data is ON.</strong> Sites with no lab readings show a demonstration
              baseline, not real figures.
            </>
          ) : (
            <>
              <strong>Sample data is OFF.</strong> Only real lab readings are shown anywhere.
            </>
          )}
          {error && <div style={{ color: '#9C0006', marginTop: 4 }}>{error}</div>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexShrink: 0 }}>
          <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {saving ? 'Saving…' : 'Sample data'}
          </span>
          <Switch value={showSampleData} onChange={handle} disabled={saving} ariaLabel="Sample data" />
        </div>
      </div>
    )
  }

  return (
    <>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '1rem', background: '#f8fafc', border: '1px solid #e2e8f0',
        borderRadius: '8px', gap: '1rem', flexWrap: 'wrap',
      }}>
        <div>
          <div style={{ fontWeight: 600, color: '#1B3A5C', marginBottom: '2px' }}>Sample / Demo Data</div>
          <div style={{ fontSize: '0.82rem', color: '#64748b', lineHeight: 1.5 }}>
            Show the built-in demonstration baseline on sites that have no lab readings yet.
            When off, no sample figure appears anywhere in the platform — pages with no live
            readings show nothing rather than a stand-in number. Turn this off for live
            production and regulatory work.
          </div>
        </div>
        <Switch value={showSampleData} onChange={handle} disabled={saving} showLabel ariaLabel="Sample data" />
      </div>
      {error && (
        <div style={{ marginTop: '0.75rem', background: '#FFC7CE', color: '#9C0006', border: '1px solid #f87171', borderRadius: 6, padding: '0.65rem 1rem', fontSize: '0.8rem' }}>
          {error}
        </div>
      )}
      <div style={{ marginTop: '0.75rem', fontSize: '0.78rem', color: '#94a3b8', lineHeight: 1.5 }}>
        {saving ? 'Saving…' : 'Saved to your user profile — applies on every browser and device you sign in from.'}
      </div>
    </>
  )
}
