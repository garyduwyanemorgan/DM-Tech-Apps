import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/react'
import './index.css'
import App from './App.tsx'
import { VersionBanner } from './components/VersionBanner'

// Clerk only accepts a live publishable key on the domain it was issued for
// (clerk.gdm-enviro.com), so the live key cannot authenticate against localhost.
// Keyed off the actual hostname rather than the Vite mode, so a production build
// served locally by FastAPI still picks the dev instance.
const IS_LOCALHOST = ['localhost', '127.0.0.1', '[::1]'].includes(
  window.location.hostname,
)

const DEV_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_DEV_PUBLISHABLE_KEY as string
const LIVE_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string

const PUBLISHABLE_KEY =
  (IS_LOCALHOST && DEV_PUBLISHABLE_KEY) || LIVE_PUBLISHABLE_KEY

if (!PUBLISHABLE_KEY) {
  console.warn('Missing VITE_CLERK_PUBLISHABLE_KEY — add it to frontend/.env.local')
} else if (IS_LOCALHOST && !DEV_PUBLISHABLE_KEY) {
  // The backend derives its JWKS URL from its own key, so a mismatch here 401s
  // every authenticated request rather than failing at sign-in.
  console.warn(
    'On localhost with no VITE_CLERK_DEV_PUBLISHABLE_KEY — falling back to the ' +
      'live key, which Clerk will reject on this origin. Add a pk_test_ key to ' +
      'frontend/.env.local (and clerk.dev_publishable_key to .streamlit/secrets.toml).',
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY || ''} afterSignOutUrl="/">
      <VersionBanner />
      <App />
    </ClerkProvider>
  </StrictMode>,
)
