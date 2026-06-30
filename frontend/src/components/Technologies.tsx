import React from 'react'
import { PageHeader } from './PageHeader'
import { ENZYME_TOOLKIT, BACTERIAL_CONSORTIUM } from '../constants'

const THREE_PILLAR_DATA = [
  {
    technology: 'Ultrasonic (MPC-Buoy)',
    responseTime: 'Hours',
    mechanism: 'Gas vesicle collapse → buoyancy loss → algae sink',
    bestAgainst: 'Cyanobacteria',
    limitation: "Doesn't remove nutrients; algae can adapt",
    role: 'Surface bloom prevention (fast response)',
  },
  {
    technology: 'Enzyme Bioremediation',
    responseTime: 'Days–Weeks',
    mechanism: 'Cell lysis by enzymes + nutrient competition by bacteria',
    bestAgainst: 'All species + sludge',
    limitation: 'Requires DO > 2 mg/L; needs halotolerant strains',
    role: 'Root cause treatment',
  },
  {
    technology: 'Aeration & Mixing',
    responseTime: 'Continuous',
    mechanism: 'Destratification + oxygenation + sediment P lock',
    bestAgainst: 'All (enables other treatments)',
    limitation: 'Undersized systems feed blooms',
    role: 'Foundation (everything depends on this)',
  },
]

const AERATION_MECHANISMS = [
  { num: 1, mechanism: 'Destratification',   how: 'Breaks thermal + salinity layers',                dubaiRelevance: 'MOST IMPORTANT — breaks TSE incubator' },
  { num: 2, mechanism: 'Light Disruption',    how: 'Algae circulated below photic zone',              dubaiRelevance: 'High PAR makes this very effective' },
  { num: 3, mechanism: 'Sediment P Lock',     how: 'Oxygenated bottom water binds Fe³⁺-PO₄',         dubaiRelevance: 'Can reduce internal P 50–80%' },
  { num: 4, mechanism: 'Bacterial Boost',     how: 'DO > 4 mg/L enables aerobic bacteria',            dubaiRelevance: 'Without this, enzymes = waste of money' },
  { num: 5, mechanism: 'CO₂ Off-gassing',     how: 'Removes excess CO₂; shifts pH',                  dubaiRelevance: 'Secondary benefit' },
]

const suitabilityColor = (s: string): React.CSSProperties => {
  if (s.startsWith('ESSENTIAL')) return { background: '#FFC7CE', color: '#9C0006' }
  if (s.startsWith('HIGH'))      return { background: '#C6EFCE', color: '#006100' }
  return                                  { background: '#FFEB9C', color: '#856404' }
}

const TABLE_HEAD_STYLE: React.CSSProperties = {
  background: '#f8fafc',
  color: '#64748b',
  padding: '10px 14px',
  textAlign: 'left',
  fontSize: '0.78rem',
  fontWeight: 700,
  letterSpacing: '0.05em',
  textTransform: 'uppercase',
  whiteSpace: 'nowrap',
  borderBottom: '2px solid #e2e8f0',
}

const TD: React.CSSProperties = {
  padding: '10px 14px',
  fontSize: '0.85rem',
  color: '#374151',
  borderBottom: '1px solid #f1f5f9',
  verticalAlign: 'top',
}

const kpiCardStyle: React.CSSProperties = {
  flex: '1 1 200px',
  background: '#ffffff',
  border: '1px solid #e2e8f0',
  borderRadius: '12px',
  padding: '24px 20px',
  textAlign: 'center',
  boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
}

export const Technologies: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '28px', padding: '8px 0' }}>

      <PageHeader title="Intervention Technologies" subtitle="Three-Pillar System: Ultrasound + Enzymes + Aeration" />

      {/* 2. THREE-PILLAR COMPARISON TABLE */}
      <div className="glass-card">
        <h2 style={{ color: '#1B3A5C', marginBottom: '16px', fontSize: '1.1rem', fontWeight: 700 }}>
          Three-Pillar Comparison
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px' }}>
            <thead>
              <tr>
                {['Technology', 'Response Time', 'Mechanism', 'Best Against', 'Limitation', 'Role'].map(h => (
                  <th key={h} style={TABLE_HEAD_STYLE}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {THREE_PILLAR_DATA.map((row, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? '#f8fafc' : 'transparent' }}>
                  <td style={{ ...TD, fontWeight: 600, color: '#1B3A5C', whiteSpace: 'nowrap' }}>{row.technology}</td>
                  <td style={{ ...TD, whiteSpace: 'nowrap' }}>{row.responseTime}</td>
                  <td style={TD}>{row.mechanism}</td>
                  <td style={TD}>{row.bestAgainst}</td>
                  <td style={{ ...TD, color: '#9C0006' }}>{row.limitation}</td>
                  <td style={{ ...TD, color: '#006100', fontWeight: 600 }}>{row.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 3. INTEGRATION LOGIC VISUAL */}
      <div className="glass-card">
        <h2 style={{ color: '#1B3A5C', marginBottom: '20px', fontSize: '1.1rem', fontWeight: 700 }}>
          Integration Logic
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '12px', justifyContent: 'center' }}>
          {/* Box 1 — Aeration */}
          <div style={{
            flex: '1 1 180px',
            background: '#D6E4F0',
            border: '1.5px solid #93c5fd',
            borderRadius: '12px',
            padding: '18px 16px',
            textAlign: 'center',
          }}>
            <div style={{ color: '#1B3A5C', fontWeight: 800, fontSize: '1rem', marginBottom: '6px' }}>AERATION</div>
            <div style={{ color: '#2E5D8A', fontSize: '0.8rem', fontWeight: 600, marginBottom: '4px' }}>Foundation</div>
            <div style={{ color: '#374151', fontSize: '0.78rem' }}>Enables everything else</div>
          </div>

          <div style={{ color: '#64748b', fontSize: '1.8rem', fontWeight: 700, flexShrink: 0 }}>→</div>

          {/* Box 2 — Enzymes */}
          <div style={{
            flex: '1 1 180px',
            background: '#C6EFCE',
            border: '1.5px solid #86efac',
            borderRadius: '12px',
            padding: '18px 16px',
            textAlign: 'center',
          }}>
            <div style={{ color: '#006100', fontWeight: 800, fontSize: '1rem', marginBottom: '6px' }}>ENZYMES</div>
            <div style={{ color: '#006100', fontSize: '0.8rem', fontWeight: 600, marginBottom: '4px' }}>Root Cause</div>
            <div style={{ color: '#374151', fontSize: '0.78rem' }}>Nutrient removal + sludge</div>
          </div>

          <div style={{ color: '#64748b', fontSize: '1.8rem', fontWeight: 700, flexShrink: 0 }}>→</div>

          {/* Box 3 — Ultrasound */}
          <div style={{
            flex: '1 1 180px',
            background: '#EDE9FE',
            border: '1.5px solid #c4b5fd',
            borderRadius: '12px',
            padding: '18px 16px',
            textAlign: 'center',
          }}>
            <div style={{ color: '#5b21b6', fontWeight: 800, fontSize: '1rem', marginBottom: '6px' }}>ULTRASOUND</div>
            <div style={{ color: '#6d28d9', fontSize: '0.8rem', fontWeight: 600, marginBottom: '4px' }}>Fast Response</div>
            <div style={{ color: '#374151', fontSize: '0.78rem' }}>Surface bloom prevention</div>
          </div>
        </div>
      </div>

      {/* 4. AERATION MECHANISMS TABLE */}
      <div className="glass-card">
        <h2 style={{ color: '#1B3A5C', marginBottom: '16px', fontSize: '1.1rem', fontWeight: 700 }}>
          Aeration — Five Anti-Algae Mechanisms
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '560px' }}>
            <thead>
              <tr>
                {['#', 'Mechanism', 'How', 'Dubai Relevance'].map(h => (
                  <th key={h} style={TABLE_HEAD_STYLE}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {AERATION_MECHANISMS.map((row, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? '#f8fafc' : 'transparent' }}>
                  <td style={{ ...TD, color: '#1B3A5C', fontWeight: 700, width: '36px' }}>{row.num}</td>
                  <td style={{ ...TD, fontWeight: 600, color: '#1B3A5C', whiteSpace: 'nowrap' }}>{row.mechanism}</td>
                  <td style={TD}>{row.how}</td>
                  <td style={{ ...TD, color: row.num === 1 ? '#856404' : row.num === 4 ? '#9C0006' : '#64748b' }}>
                    {row.dubaiRelevance}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 5. UNDER-AERATION WARNING */}
      <div style={{
        background: '#FFEB9C',
        border: '1.5px solid #fcd34d',
        borderRadius: '12px',
        padding: '18px 20px',
        display: 'flex',
        gap: '12px',
        alignItems: 'flex-start',
      }}>
        <span style={{ fontSize: '1.4rem', flexShrink: 0 }}>⚠</span>
        <div>
          <span style={{ color: '#856404', fontWeight: 700 }}>Under-aeration danger: </span>
          <span style={{ color: '#374151', fontSize: '0.9rem' }}>
            Undersized aeration systems bring nutrient-laden bottom water to the surface without fully mixing
            → feeds the bloom instead of suppressing it. Must size for complete water column mixing.
          </span>
        </div>
      </div>

      {/* 6. ENZYME TOOLKIT TABLE */}
      <div className="glass-card">
        <h2 style={{ color: '#1B3A5C', marginBottom: '16px', fontSize: '1.1rem', fontWeight: 700 }}>
          Enzyme Toolkit
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '660px' }}>
            <thead>
              <tr>
                {['Enzyme', 'Target Substrate', 'Optimal pH', 'Optimal Temp', 'Dubai Working Range', 'Species Specificity'].map(h => (
                  <th key={h} style={TABLE_HEAD_STYLE}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ENZYME_TOOLKIT.map((row, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? '#f8fafc' : 'transparent' }}>
                  <td style={{ ...TD, fontWeight: 700, color: '#1B3A5C', whiteSpace: 'nowrap' }}>{row.enzyme}</td>
                  <td style={TD}>{row.target}</td>
                  <td style={{ ...TD, whiteSpace: 'nowrap' }}>{row.ph}</td>
                  <td style={{ ...TD, whiteSpace: 'nowrap' }}>{row.temp}</td>
                  <td style={{ ...TD, color: '#006100', fontWeight: 600 }}>{row.dubaiRange}</td>
                  <td style={TD}>{row.species}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 7. BACTERIAL CONSORTIUM TABLE */}
      <div className="glass-card">
        <h2 style={{ color: '#1B3A5C', marginBottom: '16px', fontSize: '1.1rem', fontWeight: 700 }}>
          Bacterial Consortium
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '660px' }}>
            <thead>
              <tr>
                {['Genus', 'Key Species', 'Salt Tolerance', 'Primary Role', 'Dubai Suitability', 'Spore-Forming'].map(h => (
                  <th key={h} style={TABLE_HEAD_STYLE}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {BACTERIAL_CONSORTIUM.map((row, i) => {
                const suitStyle = suitabilityColor(row.suitability)
                return (
                  <tr key={i} style={{ background: i % 2 === 0 ? '#f8fafc' : 'transparent' }}>
                    <td style={{ ...TD, fontWeight: 700, color: '#1B3A5C' }}>{row.genus}</td>
                    <td style={{ ...TD, fontStyle: 'italic', color: '#64748b' }}>{row.species}</td>
                    <td style={TD}>{row.saltTolerance}</td>
                    <td style={TD}>{row.role}</td>
                    <td style={{ ...TD }}>
                      <span style={{
                        ...suitStyle,
                        borderRadius: '6px',
                        padding: '3px 10px',
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        display: 'inline-block',
                      }}>
                        {row.suitability}
                      </span>
                    </td>
                    <td style={{ ...TD, textAlign: 'center' }}>
                      {row.sporeForming
                        ? <span className="badge badge-green">Yes</span>
                        : <span className="badge badge-red">No</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* 8. CRITICAL HALOTOLERANT CALLOUT */}
      <div style={{
        background: '#FFF0F0',
        border: '1.5px solid #fecaca',
        borderRadius: '12px',
        padding: '18px 20px',
        display: 'flex',
        gap: '12px',
        alignItems: 'flex-start',
      }}>
        <span style={{ fontSize: '1.4rem', flexShrink: 0 }}>!</span>
        <div>
          <span style={{ color: '#9C0006', fontWeight: 700 }}>Critical: </span>
          <span style={{ color: '#374151', fontSize: '0.9rem' }}>
            Standard freshwater bio-enzyme products FAIL at Dubai salinities (45–60 PSU) and temperatures (30–38°C).
            Must use Gulf-adapted halotolerant strains. Halomonas is essential for bulk lagoon water above 50 PSU.
          </span>
        </div>
      </div>

      {/* 9. AL QUDRA CASE STUDY */}
      <div className="glass-card">
        <h2 style={{ color: '#1B3A5C', marginBottom: '20px', fontSize: '1.1rem', fontWeight: 700 }}>
          Al Qudra Case Study
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px' }}>
          <div style={kpiCardStyle}>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#006100', marginBottom: '6px' }}>-50%</div>
            <div style={{ color: '#374151', fontWeight: 600, fontSize: '0.92rem', marginBottom: '4px' }}>Total Algae</div>
            <div style={{ color: '#64748b', fontSize: '0.8rem' }}>100 → 50 µg/L Chl-a</div>
          </div>
          <div style={kpiCardStyle}>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#9C0006', marginBottom: '6px' }}>-73%</div>
            <div style={{ color: '#374151', fontWeight: 600, fontSize: '0.92rem', marginBottom: '4px' }}>Cyanobacteria</div>
            <div style={{ color: '#64748b', fontSize: '0.8rem' }}>675 → 180 µg/L phycocyanin</div>
          </div>
          <div style={kpiCardStyle}>
            <div style={{ fontSize: '2rem', fontWeight: 800, color: '#2E5D8A', marginBottom: '6px' }}>60 days</div>
            <div style={{ color: '#374151', fontWeight: 600, fontSize: '0.92rem', marginBottom: '4px' }}>Treatment Duration</div>
            <div style={{ color: '#64748b', fontSize: '0.8rem' }}>3 MPC-Buoy units deployed</div>
          </div>
        </div>
      </div>

    </div>
  )
}
