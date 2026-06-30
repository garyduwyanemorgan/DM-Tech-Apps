import { SignIn } from '@clerk/react'
import { Waves } from 'lucide-react'

export const Login: React.FC = () => (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      width: '100vw',
      background: 'linear-gradient(135deg, #f0f4f8 0%, #e8f0fe 100%)',
      gap: '1.5rem',
    }}
  >
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.6rem' }}>
      <div
        style={{
          background: 'linear-gradient(135deg, #1B3A5C 0%, #2E5D8A 100%)',
          borderRadius: '14px',
          padding: '0.8rem',
          display: 'flex',
        }}
      >
        <Waves size={32} color="#ffffff" />
      </div>
      <h1 style={{ margin: 0, fontSize: '1.6rem', color: '#1B3A5C', fontWeight: 700 }}>
        Dubai Lagoons
      </h1>
      <p style={{ margin: 0, color: '#64748b', fontSize: '0.875rem', textAlign: 'center', maxWidth: 280 }}>
        Water Quality Compliance &amp; Management Platform
      </p>
    </div>
    <SignIn />
  </div>
)
