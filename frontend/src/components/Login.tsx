import { useState } from 'react'
import { SignIn, SignUp } from '@clerk/react'
import { Waves } from 'lucide-react'

// Invited users arrive from Clerk's email with a __clerk_ticket in the URL. That
// requires the SignUp flow (they set their own password) rather than SignIn.
const hasInvitationTicket = (): boolean =>
  new URLSearchParams(window.location.search).has('__clerk_ticket')

const RequestAccess: React.FC = () => {
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSending(true)
    setError(null)
    try {
      const res = await fetch('/api/access-request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), name: name.trim(), message: message.trim() }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.detail || 'Request failed. Please try again.')
        return
      }
      setDone(true)
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSending(false)
    }
  }

  if (done) {
    return (
      <p style={{ margin: 0, color: '#006100', fontSize: '0.85rem', textAlign: 'center', maxWidth: 320 }}>
        Request sent. The site administrator will review it and email you your login details.
      </p>
    )
  }

  if (!open) {
    return (
      <p style={{ margin: 0, color: '#64748b', fontSize: '0.85rem' }}>
        No account?{' '}
        <button
          onClick={() => setOpen(true)}
          style={{ background: 'none', border: 'none', padding: 0, color: '#2E5D8A', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem', fontFamily: 'inherit', textDecoration: 'underline' }}
        >
          Request access
        </button>
      </p>
    )
  }

  return (
    <form
      onSubmit={submit}
      style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', width: 320, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '1rem', boxShadow: '0 4px 16px rgba(0,0,0,0.06)' }}
    >
      <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#1B3A5C' }}>Request access</span>
      <span style={{ fontSize: '0.75rem', color: '#64748b', lineHeight: 1.4 }}>
        Accounts are created by the site administrator. Submit your details and you will receive your login credentials by email.
      </span>
      <input
        type="email"
        required
        placeholder="Your email address *"
        value={email}
        onChange={e => setEmail(e.target.value)}
        style={{ padding: '0.45rem 0.7rem', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.85rem', fontFamily: 'inherit' }}
      />
      <input
        type="text"
        placeholder="Your name"
        value={name}
        onChange={e => setName(e.target.value)}
        style={{ padding: '0.45rem 0.7rem', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.85rem', fontFamily: 'inherit' }}
      />
      <textarea
        placeholder="Reason for access (optional)"
        value={message}
        onChange={e => setMessage(e.target.value)}
        rows={2}
        style={{ padding: '0.45rem 0.7rem', border: '1px solid #cbd5e1', borderRadius: 6, fontSize: '0.85rem', fontFamily: 'inherit', resize: 'vertical' }}
      />
      {error && <span style={{ fontSize: '0.75rem', color: '#9C0006' }}>{error}</span>}
      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
        <button
          type="button"
          onClick={() => setOpen(false)}
          disabled={sending}
          style={{ background: 'transparent', border: '1px solid #cbd5e1', borderRadius: 6, padding: '0.4rem 0.8rem', fontSize: '0.8rem', fontFamily: 'inherit', cursor: 'pointer', color: '#64748b' }}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={sending || !email.trim()}
          style={{ borderRadius: 6, padding: '0.4rem 0.9rem', fontSize: '0.8rem' }}
        >
          {sending ? 'Sending…' : 'Send request'}
        </button>
      </div>
    </form>
  )
}

export const Login: React.FC = () => {
  const invited = hasInvitationTicket()
  return (
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
        padding: '2rem 1rem',
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
          {invited ? 'Accept your invitation and set a password' : 'Water Quality Compliance & Management Platform'}
        </p>
      </div>
      {invited ? <SignUp /> : <SignIn />}
      {!invited && <RequestAccess />}
    </div>
  )
}
