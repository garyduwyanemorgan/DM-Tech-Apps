// Feature toggles — Settings › Features.
//
// Turning a feature off hides its sidebar group, its "Start here" shortcuts on
// the Home page, and bounces anyone sitting on one of its pages back to Home.
// Purely a display preference: the pages themselves stay reachable through the
// API and re-appear the moment the feature is switched back on.
//
// Persisted in localStorage (same pattern as the sidebar collapsed state), so
// the choice is per-browser. Everything defaults to ON.
import React, { createContext, useContext, useState } from 'react'

export type FeatureKey = 'intelligence' | 'reporting' | 'reference'

export interface FeatureMeta {
  key: FeatureKey
  label: string
  description: string
}

export const FEATURES: FeatureMeta[] = [
  {
    key: 'intelligence',
    label: 'Intelligence',
    description:
      'Environmental Drivers, Chemistry Loop, Ecology Loop and the Digital Twin ' +
      'Simulator — the analytical engine behind bloom forecasting and diagnosis.',
  },
  {
    key: 'reporting',
    label: 'Reporting',
    description:
      'Compliance Reporting and Management KPIs — submission-ready regulatory ' +
      'documents and portfolio performance metrics.',
  },
  {
    key: 'reference',
    label: 'Reference',
    description:
      'Seasonal Treatment Calendar, Intervention Technologies, Species Threat ' +
      'Matrix and the ML Prediction System — the platform’s knowledge library.',
  },
]

/** Which app tabs belong to each feature. Used to hide navigation, shortcuts,
 *  and to redirect away from a page whose feature has been switched off. */
export const FEATURE_TABS: Record<FeatureKey, readonly string[]> = {
  intelligence: ['drivers', 'chemistry', 'ecology', 'simulation'],
  reporting: ['compliance', 'kpi'],
  reference: ['calendar', 'technologies', 'species', 'mlsystem'],
}

export const featureForTab = (tab: string): FeatureKey | null => {
  for (const key of Object.keys(FEATURE_TABS) as FeatureKey[]) {
    if (FEATURE_TABS[key].includes(tab)) return key
  }
  return null
}

export type FeatureFlags = Record<FeatureKey, boolean>

const DEFAULT_FLAGS: FeatureFlags = { intelligence: true, reporting: true, reference: true }

const STORAGE_KEY = 'featureToggles'

interface FeaturesContextType {
  features: FeatureFlags
  setFeature: (key: FeatureKey, value: boolean) => void
}

const FeaturesContext = createContext<FeaturesContextType | undefined>(undefined)

export const FeaturesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [features, setFeatures] = useState<FeatureFlags>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
      return { ...DEFAULT_FLAGS, ...saved }
    } catch {
      return DEFAULT_FLAGS
    }
  })

  const setFeature = (key: FeatureKey, value: boolean) => {
    const next = { ...features, [key]: value }
    setFeatures(next)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)) } catch { /* ignore */ }
  }

  return (
    <FeaturesContext.Provider value={{ features, setFeature }}>
      {children}
    </FeaturesContext.Provider>
  )
}

export const useFeatures = () => {
  const context = useContext(FeaturesContext)
  if (!context) throw new Error('useFeatures must be used within FeaturesProvider')
  return context
}
