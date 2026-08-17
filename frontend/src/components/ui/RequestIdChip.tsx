// The correlation id, shown so a user can quote it.
//
// Nothing else in the UI exposes it, so a support conversation currently starts
// from "it broke this morning" rather than from an id that resolves to exact
// audit_events and workflow_events rows. Rendered small and monospace: it is a
// reference to read out or paste, not a headline.
import React, { useState } from 'react'
import { COLORS } from '../../lib/tokens'

export interface RequestIdChipProps {
  requestId: string | null
  /** True when this is the last id seen rather than this request's own. */
  approximate?: boolean
}

export const RequestIdChip: React.FC<RequestIdChipProps> = ({ requestId, approximate }) => {
  const [copied, setCopied] = useState(false)
  if (!requestId) return null

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(requestId)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard access can be denied or unavailable over plain http. The id
      // is on screen and selectable regardless, so this is not worth an error.
    }
  }

  return (
    <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: '12px', color: COLORS.slate }}>
        {approximate ? 'Last reference id (approximate):' : 'Reference id:'}
      </span>
      <code
        style={{
          fontSize: '12px',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          background: '#FFFFFF',
          border: `1px solid ${COLORS.border}`,
          borderRadius: 6,
          padding: '2px 6px',
          color: COLORS.ink,
          userSelect: 'all',
        }}
      >
        {requestId}
      </code>
      <button
        type="button"
        onClick={copy}
        style={{
          fontSize: '12px',
          background: 'transparent',
          border: 'none',
          color: COLORS.accent,
          cursor: 'pointer',
          padding: 0,
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}
