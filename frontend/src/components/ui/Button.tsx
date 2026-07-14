// Design-system button (GDM Lagoons Design System — Buttons).
// Five variants x three sizes. Disabled state overrides any variant.
import React, { useState } from 'react'
import { COLORS } from '../../lib/tokens'

export type ButtonVariant = 'primary' | 'navy' | 'secondary' | 'ghost' | 'destructive'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANT: Record<ButtonVariant, { base: React.CSSProperties; hover: React.CSSProperties }> = {
  primary: {
    base: { background: COLORS.accent, color: '#ffffff', border: 'none' },
    hover: { filter: 'brightness(1.1)' },
  },
  navy: {
    base: { background: COLORS.navy, color: '#ffffff', border: 'none' },
    hover: { filter: 'brightness(1.15)' },
  },
  secondary: {
    base: { background: '#ffffff', color: COLORS.ink, border: '1px solid #CBD5E1' },
    hover: { background: COLORS.surface },
  },
  ghost: {
    base: { background: 'transparent', color: COLORS.accent, border: 'none' },
    hover: { background: '#EEF2FF' },
  },
  destructive: {
    base: { background: COLORS.critical, color: '#ffffff', border: 'none' },
    hover: { filter: 'brightness(1.1)' },
  },
}

const SIZE: Record<ButtonSize, React.CSSProperties> = {
  sm: { fontSize: '13px', padding: '7px 14px', borderRadius: 7 },
  md: { fontSize: '15px', padding: '11px 22px', borderRadius: 8 },
  lg: { fontSize: '17px', padding: '14px 28px', borderRadius: 9 },
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  disabled,
  style,
  children,
  ...rest
}) => {
  const [hovered, setHovered] = useState(false)
  const v = VARIANT[variant]

  const computed: React.CSSProperties = disabled
    ? { background: '#E2E8F0', color: '#94A3B8', border: 'none', cursor: 'not-allowed' }
    : { ...v.base, ...(hovered ? v.hover : {}), cursor: 'pointer' }

  return (
    <button
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        fontWeight: 600,
        fontFamily: 'inherit',
        lineHeight: 1.2,
        transition: 'background 0.15s, filter 0.15s',
        ...SIZE[size],
        ...computed,
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  )
}
