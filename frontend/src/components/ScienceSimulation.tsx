import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { Play, TrendingDown, Clock, Activity } from 'lucide-react'
import { PageHeader } from './PageHeader'

interface ScienceSimulationProps {
  activeSite: string
}

export const ScienceSimulation: React.FC<ScienceSimulationProps> = ({ activeSite }) => {
  const { organizationId, token } = useAuth()
  const [params, setParams] = useState({
    temperature: 30.0, phosphate: 0.15, ammonia: 0.8,
    dissolved_oxygen: 4.5, salinity: 46.0,
    volume_m3: 150000.0, inflow_m3_day: 5000.0,
    outflow_m3_day: 5000.0, recirculation_m3_day: 10000.0,
    sediment_state: 'normal',
    intervention: 'reduce_phosphate', magnitude: 0.5
  })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setParams((prev) => ({ ...prev, [name]: parseFloat(value) || value }))
  }

  const handleSimulate = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const headers: HeadersInit = {
        'Content-Type': 'application/json'
      }
      if (organizationId) headers['X-Organization-ID'] = organizationId
      if (token) headers['Authorization'] = `Bearer ${token}`

      const payload = {
        temperature: params.temperature,
        phosphate: params.phosphate,
        ammonia: params.ammonia,
        dissolved_oxygen: params.dissolved_oxygen,
        salinity: params.salinity,
        volume_m3: params.volume_m3,
        inflow_m3_day: params.inflow_m3_day,
        outflow_m3_day: params.outflow_m3_day,
        recirculation_m3_day: params.recirculation_m3_day,
        sediment_state: params.sediment_state,
        intervention: params.intervention,
        intervention_magnitude: params.magnitude
      }

      const res = await fetch('/api/science/simulate', {
        method: 'POST',
        headers,
        body: JSON.stringify(payload)
      })
      const data = await res.json()
      if (res.ok) {
        setResult(data)
      } else {
        setError(data.detail || 'Simulation run failed.')
      }
    } catch (err) {
      setError('An error occurred during simulation.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: '1000px' }}>
      <PageHeader title="Digital Twin Simulator" subtitle={`Run management simulations on ${activeSite || 'your lagoon'} to forecast bloom reduction`} />

      {error && (
        <div style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '1rem', borderRadius: '8px', marginBottom: '1.5rem' }}>
          {error}
        </div>
      )}

      <div className="sim-grid">
        {/* Parameters Form */}
        <form onSubmit={handleSimulate} className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <h3>Simulation Parameters</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ fontSize: '0.8rem', opacity: 0.8, display: 'block', marginBottom: '0.25rem' }}>Temp (°C)</label>
              <input type="number" step="0.1" name="temperature" value={params.temperature} onChange={handleInputChange} />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', opacity: 0.8, display: 'block', marginBottom: '0.25rem' }}>Phosphate (mg/L)</label>
              <input type="number" step="0.01" name="phosphate" value={params.phosphate} onChange={handleInputChange} />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', opacity: 0.8, display: 'block', marginBottom: '0.25rem' }}>Ammonia (mg/L)</label>
              <input type="number" step="0.01" name="ammonia" value={params.ammonia} onChange={handleInputChange} />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', opacity: 0.8, display: 'block', marginBottom: '0.25rem' }}>DO (mg/L)</label>
              <input type="number" step="0.1" name="dissolved_oxygen" value={params.dissolved_oxygen} onChange={handleInputChange} />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', opacity: 0.8, display: 'block', marginBottom: '0.25rem' }}>Salinity (PSU)</label>
              <input type="number" step="0.1" name="salinity" value={params.salinity} onChange={handleInputChange} />
            </div>
            <div>
              <label style={{ fontSize: '0.8rem', opacity: 0.8, display: 'block', marginBottom: '0.25rem' }}>Volume (m³)</label>
              <input type="number" name="volume_m3" value={params.volume_m3} onChange={handleInputChange} />
            </div>
          </div>

          <h4 style={{ margin: '1rem 0 0 0' }}>digital twin intervention</h4>
          <div>
            <label style={{ fontSize: '0.85rem', opacity: 0.8, display: 'block', marginBottom: '0.5rem' }}>Intervention Strategy</label>
            <select name="intervention" value={params.intervention} onChange={handleInputChange}>
              <option value="reduce_phosphate">Reduce Phosphate Inflow</option>
              <option value="increase_circulation">Increase Aeration/Circulation</option>
              <option value="remove_sludge">Dredge Sludge/Sediment</option>
              <option value="reduce_residence_time">Flush/Reduce Residence Time</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: '0.85rem', opacity: 0.8, display: 'block', marginBottom: '0.5rem' }}>
              Intervention Strength: {Math.round(params.magnitude * 100)}%
            </label>
            <input type="range" min="0" max="1" step="0.05" name="magnitude" value={params.magnitude} onChange={handleInputChange} />
          </div>

          <button type="submit" disabled={loading} style={{ marginTop: '1rem', gap: '0.5rem' }}>
            <Play size={18} />
            {loading ? 'Running Digital Twin...' : 'Simulate Intervention'}
          </button>
        </form>

        {/* Results Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div className="glass-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', padding: '2.5rem', textAlign: 'center', minHeight: '300px' }}>
            {!result ? (
              <div style={{ opacity: 0.5 }}>
                <Activity size={48} style={{ marginBottom: '1rem' }} />
                <h3>Simulation Results Pending</h3>
                <p style={{ fontSize: '0.9rem' }}>Configure intervention parameters and run the simulator to predict bloom mitigation impact.</p>
              </div>
            ) : (
              <div style={{ width: '100%' }}>
                <h3 style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '0.75rem', marginBottom: '1.5rem' }}>Simulation Forecast</h3>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
                  <div className="glass-card" style={{ padding: '1rem', textAlign: 'center' }}>
                    <TrendingDown size={28} color="#10b981" style={{ margin: '0 auto 0.5rem auto' }} />
                    <span style={{ fontSize: '0.75rem', opacity: 0.6, textTransform: 'uppercase' }}>Bloom Reduction</span>
                    <h2 style={{ fontSize: '1.75rem', margin: '0.25rem 0 0 0', color: '#10b981' }}>
                      {Math.round(result.probability_reduction_pct)}%
                    </h2>
                  </div>

                  <div className="glass-card" style={{ padding: '1rem', textAlign: 'center' }}>
                    <Clock size={28} color="#6366f1" style={{ margin: '0 auto 0.5rem auto' }} />
                    <span style={{ fontSize: '0.75rem', opacity: 0.6, textTransform: 'uppercase' }}>Time to Effect</span>
                    <h2 style={{ fontSize: '1.75rem', margin: '0.25rem 0 0 0', color: '#6366f1' }}>
                      {result.days_to_effect} Days
                    </h2>
                  </div>
                </div>

                <div className="glass-card" style={{ textAlign: 'left', background: 'rgba(99, 102, 241, 0.05)', borderColor: 'rgba(99, 102, 241, 0.15)' }}>
                  <h4 style={{ margin: '0 0 0.5rem 0', color: '#818cf8' }}>Mitigation Analysis</h4>
                  <p style={{ margin: 0, fontSize: '0.92rem', opacity: 0.9, lineHeight: 1.6 }}>
                    Applying this intervention mitigates algae blooms by suppressing key nutrient loading.
                    The forecast predicts stability in water parameters within {result.days_to_effect} days of implementation.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
