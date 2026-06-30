import React from 'react';
import { SPECIES_PROFILES } from '../constants';
import { PageHeader } from './PageHeader';

const HISTORICAL_BLOOM_EVENTS = [
  { year: '2008–09', location: 'Arabian Gulf',     species: 'Cochlodinium',  impact: '1,200 km affected',       lesson: 'Gulf-wide monitoring needed' },
  { year: '2017',    location: 'Off Dubai coast',  species: 'Noctiluca',     impact: 'Visible bloom',            lesson: 'Winter blooms also possible' },
  { year: '2018',    location: 'Al Qudra Lakes',   species: 'Cyanobacteria', impact: 'Recreational system',      lesson: 'MPC-Buoy reduced cyano 73% in 60 days' },
  { year: '2021',    location: 'Kuwait Bay',        species: 'Chattonella',   impact: '435,000 cells/L',          lesson: 'Dust storms trigger blooms within days' },
];

function categoryBg(category: string): React.CSSProperties {
  if (category === 'HIGH THREAT') return { backgroundColor: '#FFC7CE', color: '#9C0006' };
  if (category === 'MODERATE')    return { backgroundColor: '#FFEB9C', color: '#856404' };
  return { backgroundColor: '#D6E4F0', color: '#1B3A5C' };
}

function threatBadgeClass(threat: string): string {
  if (threat === 'HIGH')     return 'badge badge-red';
  if (threat === 'MODERATE') return 'badge badge-yellow';
  return 'badge badge-blue';
}

export const Species: React.FC = () => {
  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>

      <PageHeader title="Species Threat Matrix" subtitle="Algae Identification & Response Guide" />

      {/* 2. SPECIES SUMMARY TABLE */}
      <div className="glass-card" style={{ marginBottom: '28px', overflowX: 'auto' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '16px', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Species Summary
        </h2>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '900px', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
              {['Category', 'Group', 'Key Species', 'Salinity', 'Temp', 'Toxin', 'Threat', 'Season', 'Treatment'].map(col => (
                <th key={col} style={{
                  padding: '10px 12px',
                  textAlign: 'left',
                  color: '#94a3b8',
                  fontWeight: 600,
                  fontSize: '0.75rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  whiteSpace: 'nowrap',
                }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SPECIES_PROFILES.map((sp, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #f1f5f9', transition: 'background 0.15s' }}>
                <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                  <span style={{
                    ...categoryBg(sp.category),
                    padding: '3px 10px',
                    borderRadius: '9999px',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    letterSpacing: '0.04em',
                  }}>
                    {sp.category}
                  </span>
                </td>
                <td style={{ padding: '10px 12px', color: sp.color, fontWeight: 600, whiteSpace: 'nowrap' }}>{sp.group}</td>
                <td style={{ padding: '10px 12px', color: '#374151', fontStyle: 'italic', maxWidth: '180px' }}>{sp.keySpecies}</td>
                <td style={{ padding: '10px 12px', color: '#64748b', whiteSpace: 'nowrap' }}>{sp.salinity}</td>
                <td style={{ padding: '10px 12px', color: '#64748b', whiteSpace: 'nowrap' }}>{sp.temp}</td>
                <td style={{ padding: '10px 12px', color: '#64748b', maxWidth: '160px', fontSize: '0.8rem' }}>{sp.toxin}</td>
                <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                  <span className={threatBadgeClass(sp.threat)}>{sp.threat}</span>
                </td>
                <td style={{ padding: '10px 12px', color: '#64748b', whiteSpace: 'nowrap', fontSize: '0.8rem' }}>{sp.season}</td>
                <td style={{ padding: '10px 12px', color: '#374151', fontSize: '0.8rem' }}>{sp.treatment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 3. SENSOR-BASED SPECIES ID */}
      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '28px' }}>
        {/* Left — Cyanobacteria Dominant */}
        <div style={{
          flex: '1 1 300px',
          background: '#FFF0F0',
          border: '1px solid #fecaca',
          borderRadius: '12px',
          padding: '22px 24px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ef4444', flexShrink: 0 }} />
            <span style={{ fontFamily: 'monospace', color: '#9C0006', fontWeight: 700, fontSize: '0.95rem' }}>
              Phycocyanin : Chl-a &gt; 0.5
            </span>
          </div>
          <p style={{ color: '#9C0006', fontWeight: 700, fontSize: '1rem', marginBottom: '8px' }}>
            Cyanobacteria Dominant
          </p>
          <p style={{ color: '#9C0006', fontSize: '0.875rem', lineHeight: 1.6 }}>
            Activate ultrasound + cyano-specific enzymes. Prioritise phycocyanin monitoring. Watch for hepatotoxin accumulation.
          </p>
        </div>

        {/* Right — Other Species Dominant */}
        <div style={{
          flex: '1 1 300px',
          background: '#D6E4F0',
          border: '1px solid #93c5fd',
          borderRadius: '12px',
          padding: '22px 24px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#3b82f6', flexShrink: 0 }} />
            <span style={{ fontFamily: 'monospace', color: '#1B3A5C', fontWeight: 700, fontSize: '0.95rem' }}>
              Phycocyanin : Chl-a &lt; 0.5
            </span>
          </div>
          <p style={{ color: '#1B3A5C', fontWeight: 700, fontSize: '1rem', marginBottom: '8px' }}>
            Other Species Dominant
          </p>
          <p style={{ color: '#1B3A5C', fontSize: '0.875rem', lineHeight: 1.6 }}>
            Standard treatment protocol — aeration priority. Monitor for dinoflagellate species. Adjust enzyme blend to broad-spectrum.
          </p>
        </div>
      </div>

      {/* 4. DUAL BLOOM CALLOUT */}
      <div style={{
        background: '#FFEB9C',
        border: '1px solid #fcd34d',
        borderRadius: '12px',
        padding: '20px 24px',
        marginBottom: '28px',
        display: 'flex',
        gap: '14px',
        alignItems: 'flex-start',
      }}>
        <span style={{ fontSize: '1.3rem', flexShrink: 0, marginTop: '2px' }}>⚠</span>
        <div>
          <p style={{ color: '#856404', fontWeight: 700, fontSize: '0.95rem', marginBottom: '6px' }}>
            Dual Bloom Regime Alert
          </p>
          <p style={{ color: '#374151', fontSize: '0.875rem', lineHeight: 1.7 }}>
            Two simultaneous bloom regimes: Dubai lagoons host <strong>marine dinoflagellates</strong> in bulk water AND{' '}
            <strong>freshwater cyanobacteria</strong> in the TSE surface lens. Both{' '}
            <strong>chlorophyll-a</strong> (total biomass) and <strong>phycocyanin</strong> (cyano-specific) must be monitored.
          </p>
        </div>
      </div>

      {/* 5. DETAILED SPECIES CARDS */}
      <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '16px', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        Detailed Species Profiles
      </h2>
      <div className="grid-cols-3" style={{ marginBottom: '32px' }}>
        {SPECIES_PROFILES.map((sp, i) => (
          <div
            key={i}
            className="glass-card"
            style={{ borderLeft: `4px solid ${sp.color}`, padding: '20px' }}
          >
            {/* Group + Category */}
            <div style={{ marginBottom: '12px' }}>
              <p style={{ color: sp.color, fontWeight: 700, fontSize: '1rem', marginBottom: '4px' }}>
                {sp.group}
              </p>
              <span style={{
                ...categoryBg(sp.category),
                padding: '2px 10px',
                borderRadius: '9999px',
                fontSize: '0.68rem',
                fontWeight: 700,
                letterSpacing: '0.04em',
              }}>
                {sp.category}
              </span>
            </div>

            {/* Key species */}
            <p style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '0.8rem', marginBottom: '14px', lineHeight: 1.5 }}>
              {sp.keySpecies}
            </p>

            {/* 2x2 grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '14px' }}>
              {[
                { label: 'Salinity', value: sp.salinity },
                { label: 'Temp',     value: sp.temp },
                { label: 'Toxin',    value: sp.toxin },
                { label: 'Season',   value: sp.season },
              ].map(item => (
                <div key={item.label} style={{
                  background: '#f8fafc',
                  borderRadius: '8px',
                  padding: '8px 10px',
                }}>
                  <p style={{ color: '#94a3b8', fontSize: '0.68rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '3px' }}>
                    {item.label}
                  </p>
                  <p style={{ color: '#374151', fontSize: '0.78rem', lineHeight: 1.4 }}>
                    {item.value}
                  </p>
                </div>
              ))}
            </div>

            {/* Treatment */}
            <div style={{
              background: `rgba(${sp.color === '#e74c3c' || sp.color === '#c0392b' ? '239,68,68' : sp.color === '#f39c12' || sp.color === '#e67e22' ? '245,158,11' : '59,130,246'},0.1)`,
              border: `1px solid ${sp.color}40`,
              borderRadius: '8px',
              padding: '8px 10px',
            }}>
              <p style={{ color: '#94a3b8', fontSize: '0.68rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '3px' }}>
                Treatment
              </p>
              <p style={{ color: '#1B3A5C', fontSize: '0.8rem', fontWeight: 600 }}>
                {sp.treatment}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* 6. HISTORICAL BLOOM EVENTS TABLE */}
      <div className="glass-card" style={{ overflowX: 'auto' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '16px', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Historical Bloom Events
        </h2>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
              {['Year', 'Location', 'Species', 'Impact', 'Lesson'].map(col => (
                <th key={col} style={{
                  padding: '10px 14px',
                  textAlign: 'left',
                  color: '#94a3b8',
                  fontWeight: 600,
                  fontSize: '0.75rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  whiteSpace: 'nowrap',
                }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {HISTORICAL_BLOOM_EVENTS.map((ev, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                <td style={{ padding: '11px 14px', color: '#1B3A5C', fontWeight: 700, whiteSpace: 'nowrap' }}>{ev.year}</td>
                <td style={{ padding: '11px 14px', color: '#374151', whiteSpace: 'nowrap' }}>{ev.location}</td>
                <td style={{ padding: '11px 14px', color: '#9C0006', fontStyle: 'italic' }}>{ev.species}</td>
                <td style={{ padding: '11px 14px', color: '#856404' }}>{ev.impact}</td>
                <td style={{ padding: '11px 14px', color: '#94a3b8', fontSize: '0.82rem' }}>{ev.lesson}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

    </div>
  );
};
