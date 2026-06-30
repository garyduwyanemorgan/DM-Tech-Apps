import React from 'react'
import { PageHeader } from './PageHeader'
import { ML_MODELS, ENSEMBLE_WEIGHTS } from '../constants'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

const TH: React.CSSProperties = {
  padding: '10px 14px',
  textAlign: 'left',
  color: '#64748b',
  fontWeight: 700,
  whiteSpace: 'nowrap',
  background: '#f8fafc',
  borderBottom: '2px solid #e2e8f0',
  textTransform: 'uppercase',
  fontSize: '0.75rem',
  letterSpacing: '0.04em',
}

const TD: React.CSSProperties = {
  padding: '10px 14px',
  color: '#374151',
  fontSize: '0.875rem',
  borderBottom: '1px solid #f1f5f9',
}

export const MLSystem: React.FC = () => {
  const roadmap = [
    {
      phase: 'Phase 1',
      duration: '1–3 months',
      name: 'Launch',
      activities: 'Deploy sensors, build RF, Option A ensemble',
      outcome: '1–3 day alerts',
    },
    {
      phase: 'Phase 2',
      duration: '3–6 months',
      name: 'LSTM Integration',
      activities: 'Train LSTM on 3+ months data',
      outcome: 'Integrated prediction-to-treatment',
    },
    {
      phase: 'Phase 3',
      duration: '6–12 months',
      name: 'Production Ensemble',
      activities: 'Stacking meta-learner Option B',
      outcome: 'Full season',
    },
    {
      phase: 'Phase 4',
      duration: 'Year 2+',
      name: 'Mature Platform',
      activities: 'Conditional routing Option C, satellite',
      outcome: 'Multi-lagoon portfolio',
    },
  ]

  const architectureText = `Sensor Data (10-min) → Cleaned Time-Series
  ├── RF Path: Tabular snapshot + rolling stats (~40-60 features)
  │   └── RF/XGBoost → Chl-a prediction + SHAP values
  │
  └── LSTM Path: 7-day hourly sequence (168 timesteps)
      └── LSTM → Chl-a at +24h, +72h, +168h

Both paths → Ensemble Combiner → Bloom Probability
  └── Alert Engine → Treatment Dispatch → Dashboard`

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div style={{
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
          padding: '10px 14px',
          color: '#374151',
          fontSize: '13px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        }}>
          <p style={{ marginBottom: 6, fontWeight: 600, color: '#1B3A5C' }}>{label}</p>
          {payload.map((entry: any) => (
            <p key={entry.name} style={{ margin: '2px 0', color: entry.color, fontWeight: 600 }}>
              {entry.name}: <strong>{entry.value}%</strong>
            </p>
          ))}
        </div>
      )
    }
    return null
  }

  return (
    <div style={{ padding: '24px 0' }}>

      <PageHeader title="ML Prediction System" subtitle="Architecture, Model Comparison & Performance Tracking" />

      {/* 2. MODEL COMPARISON TABLE */}
      <div className="glass-card" style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '16px' }}>
          Model Comparison
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem', minWidth: '600px' }}>
            <thead>
              <tr>
                {['Model', 'Forecast Range', 'Training Data', 'R² Score', 'Key Advantage', 'Tier', 'Production Role'].map((h) => (
                  <th key={h} style={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ML_MODELS.map((m, i) => (
                <tr key={m.model} style={{ background: i % 2 === 0 ? '#f8fafc' : 'transparent' }}>
                  <td style={{ ...TD, fontWeight: 700, color: '#1B3A5C', whiteSpace: 'nowrap' }}>{m.model}</td>
                  <td style={{ ...TD, whiteSpace: 'nowrap' }}>{m.range}</td>
                  <td style={{ ...TD, whiteSpace: 'nowrap' }}>{m.dataNeed}</td>
                  <td style={{ ...TD, fontWeight: 700, color: '#2E5D8A' }}>{m.r2}</td>
                  <td style={TD}>{m.advantage}</td>
                  <td style={TD}>
                    <span className="badge badge-blue">Tier {m.tier}</span>
                  </td>
                  <td style={{ ...TD, color: '#64748b' }}>{m.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. ENSEMBLE WEIGHTS CHART */}
      <div className="glass-card" style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '4px' }}>
          Ensemble Weights by Forecast Horizon
        </h2>
        <p style={{ color: '#64748b', fontSize: '0.82rem', marginBottom: '16px' }}>
          RF vs LSTM weighting shifts as the horizon extends
        </p>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart
            data={ENSEMBLE_WEIGHTS}
            margin={{ top: 10, right: 30, left: 0, bottom: 10 }}
            barSize={56}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="horizon"
              tick={{ fill: '#64748b', fontSize: 13 }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              domain={[0, 100]}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ color: '#64748b', fontSize: '13px', paddingTop: '8px' }} />
            <Bar dataKey="rf" name="RF" stackId="a" fill="#4472C4" label={{ position: 'inside', fill: '#fff', fontSize: 12, fontWeight: 700, formatter: (v: unknown) => `${v}%` }} />
            <Bar dataKey="lstm" name="LSTM" stackId="a" fill="#e74c3c" label={{ position: 'inside', fill: '#fff', fontSize: 12, fontWeight: 700, formatter: (v: unknown) => `${v}%` }} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 4. BLENDING OPTIONS */}
      <div className="glass-card" style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '16px' }}>
          Ensemble Blending Options
        </h2>
        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 260px', background: '#D6E4F0', border: '1px solid #93c5fd', borderRadius: '12px', padding: '18px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
              <span className="badge badge-blue">Option A</span>
              <span style={{ color: '#1B3A5C', fontWeight: 700, fontSize: '0.9rem' }}>Start Here</span>
            </div>
            <p style={{ color: '#1B3A5C', fontWeight: 600, fontSize: '0.9rem', marginBottom: '6px' }}>Horizon-weighted average</p>
            <p style={{ color: '#374151', fontSize: '0.82rem', lineHeight: 1.6 }}>Tune via grid search on validation RMSE</p>
          </div>

          <div style={{ flex: '1 1 260px', background: '#FFEB9C', border: '1px solid #fcd34d', borderRadius: '12px', padding: '18px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
              <span className="badge badge-yellow">Option B</span>
              <span style={{ color: '#856404', fontWeight: 700, fontSize: '0.9rem' }}>Production</span>
            </div>
            <p style={{ color: '#856404', fontWeight: 600, fontSize: '0.9rem', marginBottom: '6px' }}>Stacking meta-learner</p>
            <p style={{ color: '#374151', fontSize: '0.82rem', lineHeight: 1.6 }}>Logistic regression on out-of-fold predictions</p>
          </div>

          <div style={{ flex: '1 1 260px', background: '#C6EFCE', border: '1px solid #86efac', borderRadius: '12px', padding: '18px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
              <span className="badge badge-green">Option C</span>
              <span style={{ color: '#006100', fontWeight: 700, fontSize: '0.9rem' }}>Mature</span>
            </div>
            <p style={{ color: '#006100', fontWeight: 600, fontSize: '0.9rem', marginBottom: '6px' }}>Conditional routing</p>
            <p style={{ color: '#374151', fontSize: '0.82rem', lineHeight: 1.6 }}>RF-only when stable, LSTM-dominant during blooms</p>
          </div>
        </div>
      </div>

      {/* 5. INPUT VARIABLES */}
      <div className="glass-card" style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '16px' }}>
          Input Variables
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '24px' }}>
          <div>
            <h3 style={{ color: '#2E5D8A', fontWeight: 700, fontSize: '0.82rem', marginBottom: '14px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Sensor Inputs (10-min intervals)
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {[
                { dot: '#e74c3c', label: 'Chlorophyll-a (total biomass)', priority: 'CRITICAL', pClass: 'badge-red' },
                { dot: '#e74c3c', label: 'Phycocyanin (cyano-specific)', priority: 'CRITICAL', pClass: 'badge-red' },
                { dot: '#e74c3c', label: 'Dissolved Oxygen', priority: 'CRITICAL', pClass: 'badge-red' },
                { dot: '#f39c12', label: 'Water Temperature', priority: 'HIGH', pClass: 'badge-yellow' },
                { dot: '#f39c12', label: 'Salinity (surface + bulk)', priority: 'HIGH', pClass: 'badge-yellow' },
                { dot: '#3b82f6', label: 'pH', priority: 'MODERATE', pClass: 'badge-blue' },
                { dot: '#3b82f6', label: 'Turbidity', priority: 'MODERATE', pClass: 'badge-blue' },
              ].map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: item.dot, flexShrink: 0, display: 'inline-block' }} />
                    <span style={{ color: '#374151', fontSize: '0.82rem' }}>{item.label}</span>
                  </div>
                  <span className={`badge ${item.pClass}`} style={{ flexShrink: 0, fontSize: '11px' }}>{item.priority}</span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h3 style={{ color: '#2E5D8A', fontWeight: 700, fontSize: '0.82rem', marginBottom: '14px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              External APIs &amp; Derived Features
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {[
                { dot: '#e74c3c', label: 'TSE inflow volume + quality (N, P)', priority: 'CRITICAL', pClass: 'badge-red' },
                { dot: '#f39c12', label: 'Weather forecast (wind, solar, air temp)', priority: 'HIGH', pClass: 'badge-yellow' },
                { dot: '#f39c12', label: 'Dust storm index (Met Office)', priority: 'HIGH', pClass: 'badge-yellow' },
              ].map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: item.dot, flexShrink: 0, display: 'inline-block' }} />
                    <span style={{ color: '#374151', fontSize: '0.82rem' }}>{item.label}</span>
                  </div>
                  <span className={`badge ${item.pClass}`} style={{ flexShrink: 0, fontSize: '11px' }}>{item.priority}</span>
                </div>
              ))}
              {[
                'Rolling 24h stats (mean, max, min, std)',
                'Lag features (24h, 48h, 72h ago)',
                'Rate-of-change (Chl-a delta 6h/12h/24h)',
                'Cross-features (temp × nutrient proxy)',
              ].map((label) => (
                <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#94a3b8', flexShrink: 0, display: 'inline-block' }} />
                  <span style={{ color: '#64748b', fontSize: '0.82rem' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 6. ARCHITECTURE DIAGRAM */}
      <div className="glass-card" style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '16px' }}>
          System Architecture
        </h2>
        <pre style={{
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: '10px',
          padding: '20px 24px',
          fontFamily: '"Courier New", Courier, monospace',
          fontSize: '0.8rem',
          color: '#1B3A5C',
          lineHeight: 1.75,
          overflowX: 'auto',
          margin: 0,
          whiteSpace: 'pre',
        }}>
          {architectureText}
        </pre>
      </div>

      {/* 7. IMPLEMENTATION ROADMAP TABLE */}
      <div className="glass-card" style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#1B3A5C', marginBottom: '16px' }}>
          Implementation Roadmap
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem', minWidth: '500px' }}>
            <thead>
              <tr>
                {['Phase', 'Duration', 'Name', 'Key Activities', 'Outcome'].map((h) => (
                  <th key={h} style={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {roadmap.map((row, i) => {
                const phaseColors = ['#4472C4', '#3b82f6', '#f59e0b', '#10b981']
                const color = phaseColors[i] ?? '#4472C4'
                return (
                  <tr key={row.phase} style={{ background: i % 2 === 0 ? '#f8fafc' : 'transparent' }}>
                    <td style={{ padding: '10px 14px', borderBottom: '1px solid #f1f5f9', whiteSpace: 'nowrap' }}>
                      <span style={{
                        display: 'inline-block',
                        background: `${color}22`,
                        border: `1px solid ${color}66`,
                        color: color,
                        borderRadius: '6px',
                        padding: '2px 10px',
                        fontWeight: 700,
                        fontSize: '0.78rem',
                      }}>
                        {row.phase}
                      </span>
                    </td>
                    <td style={{ ...TD, whiteSpace: 'nowrap', color: '#64748b' }}>{row.duration}</td>
                    <td style={{ ...TD, fontWeight: 700, color: '#1B3A5C', whiteSpace: 'nowrap' }}>{row.name}</td>
                    <td style={TD}>{row.activities}</td>
                    <td style={{ ...TD, color: '#2E5D8A', whiteSpace: 'nowrap' }}>{row.outcome}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 8. KEY FINDING CALLOUT */}
      <div style={{
        background: '#D6E4F0',
        border: '1px solid #93c5fd',
        borderLeft: '4px solid #2E5D8A',
        borderRadius: '10px',
        padding: '18px 22px',
        display: 'flex',
        gap: '14px',
        alignItems: 'flex-start',
      }}>
        <span style={{ fontSize: '20px', flexShrink: 0, marginTop: '1px' }}>&#8505;</span>
        <p style={{ color: '#1B3A5C', fontSize: '0.875rem', lineHeight: 1.7, margin: 0 }}>
          <strong>Key research finding:</strong>{' '}
          Random Forest consistently outperforms benchmarks once training data exceeds 4 years (MAPE 16.4% lower).
          XGBoost achieved R&sup2; = 0.92 for HABs prediction.
          Operational algal bloom forecasting systems are still scarce &mdash; this is a differentiator.
        </p>
      </div>

    </div>
  )
}
