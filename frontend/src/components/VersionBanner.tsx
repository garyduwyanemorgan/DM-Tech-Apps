import React, { useEffect, useState } from 'react'

// The SPA and the API ship from one process, so they agree at deploy time. They
// disagree when a browser is holding a bundle from an older deploy — a tab left
// open across a release. That stale bundle can behave in ways the current API
// does not expect, and nothing else tells the user.
//
// Baked in at build time by vite.config.ts.
const APP_VERSION = import.meta.env.VITE_APP_VERSION

// A redeploy briefly makes the API unreachable. Treat that as "no opinion" and
// re-check once before saying anything, so a restart never flashes a warning.
const SETTLE_MS = 20_000

async function fetchApiVersion(): Promise<string | null> {
  try {
    const res = await fetch('/api/version', { cache: 'no-store' })
    if (!res.ok) return null
    const data = await res.json()
    return typeof data?.version === 'string' ? data.version : null
  } catch {
    return null
  }
}

export const VersionBanner: React.FC = () => {
  const [apiVersion, setApiVersion] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const first = await fetchApiVersion()
      if (cancelled) return
      if (!first || first === APP_VERSION) {
        setApiVersion(first)
        return
      }
      await new Promise((r) => setTimeout(r, SETTLE_MS))
      if (cancelled) return
      setApiVersion(await fetchApiVersion())
    })()
    return () => { cancelled = true }
  }, [])

  const mismatch = apiVersion !== null && apiVersion !== APP_VERSION
  if (!mismatch) return null

  return (
    <div
      role="status"
      style={{
        position: 'sticky', top: 0, zIndex: 200,
        background: '#FFEB9C', color: '#856404',
        borderBottom: '1px solid #fcd34d',
        padding: '0.6rem 1rem', fontSize: '0.82rem',
        textAlign: 'center', lineHeight: 1.5,
      }}
    >
      <strong>Version mismatch.</strong> This page was loaded from v{APP_VERSION} but the
      server is running v{apiVersion}. Hard-refresh (Ctrl/⌘ + Shift + R) to load the
      current build.
    </div>
  )
}
