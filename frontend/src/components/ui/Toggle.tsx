// Design-system toggle switch (GDM Lagoons Design System — Inputs & forms).
// Extracted from SampleDataToggle.tsx so any feature can use it; the "on"
// track uses the Accent token per the design system (was hardcoded steel
// blue). Track dimensions kept at 44x24 (existing touch target).
import React from 'react'
import { COLORS } from '../../lib/tokens'

export interface SwitchProps {
  value: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
  /** Show the "Enabled / Disabled" text beside the switch. */
  showLabel?: boolean
  ariaLabel?: string
}

export const Switch: React.FC<SwitchProps> = ({ value, onChange, disabled, showLabel, ariaLabel }) => (
  <div
    role="switch"
    aria-checked={value}
    aria-label={ariaLabel ?? 'Toggle'}
    onClick={() => !disabled && onChange(!value)}
    style={{
      display: 'flex',
      alignItems: 'center',
      cursor: disabled ? 'wait' : 'pointer',
      gap: '0.5rem',
      userSelect: 'none',
      opacity: disabled ? 0.6 : 1,
    }}
  >
    <div style={{
      width: '44px', height: '24px', borderRadius: '12px',
      background: value ? COLORS.accent : '#cbd5e1',
      position: 'relative', transition: 'background 0.2s', flexShrink: 0,
    }}>
      <div style={{
        position: 'absolute', top: '3px', left: value ? '23px' : '3px',
        width: '18px', height: '18px', borderRadius: '50%',
        background: '#ffffff', boxShadow: '0 1px 4px rgba(0,0,0,0.2)', transition: 'left 0.2s',
      }} />
    </div>
    {showLabel && (
      <span style={{ fontSize: '0.875rem', fontWeight: 600, color: value ? COLORS.navy : '#94a3b8' }}>
        {value ? 'Enabled' : 'Disabled'}
      </span>
    )}
  </div>
)
