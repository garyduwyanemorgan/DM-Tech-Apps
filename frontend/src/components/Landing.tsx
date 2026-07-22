import React, { useState } from 'react'
import { Login } from './Login'

/**
 * Public landing page — everything a client sees before signing in.
 *
 * Deliberately in front of the authenticated app, never inside it: `Login` is
 * rendered untouched when the visitor asks to sign in, so nothing behind the
 * gate changes. Colours and button texture come from the existing design
 * system (lib/tokens.ts) rather than a separate marketing palette.
 *
 * The mosaic globe is the single flourish. It rises behind the hero copy with a
 * soft glow and nothing else competes with it — no gradients on the cards, no
 * second accent, no motion beyond a slow drift. Spending the boldness in one
 * place is what keeps the rest feeling calm.
 */

const NAVY = '#1B3A5C'
const STEEL = '#2E5D8A'
const INK = '#0B1240'
const SLATE = '#64748B'
const MIST = '#D6E4F0'
const SURFACE = '#F8FAFC'
const BORDER = '#E2E8F0'
const PASS = '#27AE60'

const MONO = 'ui-monospace, "Cascadia Mono", "SF Mono", Menlo, Consolas, monospace'

const wrap: React.CSSProperties = { maxWidth: 1140, margin: '0 auto', padding: '0 clamp(1.1rem, 4vw, 2.5rem)' }

const eyebrow: React.CSSProperties = {
  fontFamily: MONO, fontSize: '0.72rem', letterSpacing: '0.16em',
  textTransform: 'uppercase', margin: '0 0 0.9rem',
}

/** Matches the app's own button: navy fill, 6px radius, steel on hover. */
const Btn: React.FC<{
  children: React.ReactNode; onClick?: () => void; variant?: 'solid' | 'ghost' | 'light'
}> = ({ children, onClick, variant = 'solid' }) => {
  const [hover, setHover] = useState(false)
  const base: React.CSSProperties = {
    font: 'inherit', fontWeight: 600, fontSize: '0.9rem', padding: '0.6rem 1.25rem',
    borderRadius: 6, cursor: 'pointer', display: 'inline-flex', alignItems: 'center',
    justifyContent: 'center', gap: '0.45rem', transition: 'background 0.15s, border-color 0.15s, color 0.15s',
  }
  const styles: Record<string, React.CSSProperties> = {
    solid: { ...base, background: hover ? STEEL : NAVY, color: '#fff', border: 'none' },
    light: { ...base, background: hover ? '#fff' : MIST, color: NAVY, border: 'none' },
    ghost: {
      ...base, background: 'transparent', color: hover ? '#fff' : 'rgba(255,255,255,0.82)',
      border: `1px solid ${hover ? 'rgba(255,255,255,0.55)' : 'rgba(255,255,255,0.28)'}`,
    },
  }
  return (
    <button type="button" onClick={onClick} style={styles[variant]}
            onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      {children}
    </button>
  )
}

const Card: React.FC<{ k: string; title: string; children: React.ReactNode }> = ({ k, title, children }) => (
  <div style={{ background: '#fff', border: `1px solid ${BORDER}`, borderRadius: 10, padding: '1.35rem' }}>
    <span style={{ ...eyebrow, color: STEEL, margin: '0 0 0.5rem', display: 'block' }}>{k}</span>
    <h3 style={{ margin: '0 0 0.4rem', fontSize: '1rem', fontWeight: 700, color: INK }}>{title}</h3>
    <p style={{ margin: 0, fontSize: '0.9rem', color: SLATE, lineHeight: 1.6 }}>{children}</p>
  </div>
)

/** Columns point at real sections of this page — no dead links to pages that
 *  do not exist yet. */
const FOOTER_COLUMNS: { title: string; links: { label: string; href: string }[] }[] = [
  {
    title: 'Platform',
    links: [
      { label: 'The problem', href: '#problem' },
      { label: 'What it catches', href: '#catches' },
      { label: 'A certificate, checked', href: '#certificate' },
      { label: 'How it works', href: '#how' },
    ],
  },
  {
    title: 'Assurance',
    links: [
      { label: 'Read from the certificate', href: '#certificate' },
      { label: 'Checked against the guideline', href: '#catches' },
      { label: 'Confirmed by a reviewer', href: '#how' },
    ],
  },
]

const SiteFooter: React.FC = () => {
  // The build stamp comes from the app's own /api/version, so the footer always
  // states what is actually deployed rather than a value baked in at build time.
  const [build, setBuild] = useState<{ version?: string; commit?: string | null }>({})
  React.useEffect(() => {
    let cancelled = false
    fetch('/api/version')
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (!cancelled && d) setBuild({ version: d.version, commit: d.commit }) })
      .catch(() => { /* the stamp is informational; its absence is not an error */ })
    return () => { cancelled = true }
  }, [])

  const link: React.CSSProperties = { color: 'rgba(255,255,255,0.68)', textDecoration: 'none' }

  return (
    <footer style={{ background: INK, color: 'rgba(255,255,255,0.68)', fontSize: '0.85rem' }}>
      <div style={{ ...wrap, display: 'grid', gap: '2rem', paddingTop: '3rem', paddingBottom: '3rem',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
        {/* Brand — the mosaic keeps its own colours; the wordmark is typeset so
            it stays crisp and needs no knocked-out background. */}
        <div style={{ gridColumn: 'span 2', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem' }}>
            <img src="/gdm-globe.png" alt="" aria-hidden="true"
                 style={{ width: 30, height: 30, borderRadius: '50%',
                          filter: 'drop-shadow(0 0 12px rgba(160,200,235,0.28))' }} />
            <span style={{ color: '#fff', fontWeight: 700, letterSpacing: '-0.01em' }}>
              GDM Environmental
            </span>
          </div>
          <p style={{ margin: '0.85rem 0 0', maxWidth: '34ch', lineHeight: 1.65 }}>
            Environmental specialists for the UAE. We check laboratory certificates
            against the guideline they cite, before they reach the regulator.
          </p>
        </div>

        {FOOTER_COLUMNS.map(col => (
          <div key={col.title}>
            <h2 style={{ margin: 0, fontSize: '0.85rem', fontWeight: 700, color: '#fff' }}>{col.title}</h2>
            <ul style={{ listStyle: 'none', margin: '0.8rem 0 0', padding: 0,
                         display: 'grid', gap: '0.55rem' }}>
              {col.links.map(l => (
                <li key={l.label}>
                  <a href={l.href} style={link}
                     onMouseEnter={e => (e.currentTarget.style.color = '#fff')}
                     onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.68)')}>
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}

        <div>
          <h2 style={{ margin: 0, fontSize: '0.85rem', fontWeight: 700, color: '#fff' }}>Contact</h2>
          <p style={{ margin: '0.8rem 0 0' }}>
            <a href="mailto:gary@gdm-enviro.com" style={link}
               onMouseEnter={e => (e.currentTarget.style.color = '#fff')}
               onMouseLeave={e => (e.currentTarget.style.color = 'rgba(255,255,255,0.68)')}>
              gary@gdm-enviro.com
            </a>
          </p>
          <p style={{ margin: '0.35rem 0 0' }}>Dubai · Abu Dhabi · GCC</p>
        </div>
      </div>

      <div style={{ ...wrap, borderTop: '1px solid rgba(255,255,255,0.10)', paddingTop: '1rem',
                    paddingBottom: '1rem', fontSize: '0.72rem', display: 'flex', flexWrap: 'wrap',
                    gap: '0.35rem 1.25rem', justifyContent: 'space-between' }}>
        <span>
          © {new Date().getFullYear()} GDM Environmental. Compliance verdicts are read from the
          certificate and confirmed by a reviewer before they are recorded.
        </span>
        <span style={{ fontFamily: MONO, color: 'rgba(255,255,255,0.40)', whiteSpace: 'nowrap' }}>
          {build.version ? `v${build.version}` : ''}{build.commit ? ` · ${build.commit}` : ''}
        </span>
      </div>
    </footer>
  )
}

export const Landing: React.FC = () => {
  const [showLogin, setShowLogin] = useState(false)
  if (showLogin) return <Login />

  const goSignIn = () => setShowLogin(true)

  return (
    <div style={{ flex: 1, minHeight: '100vh', background: '#fff', overflowX: 'hidden' }}>
      <style>{`
        @keyframes gdmDrift { from { transform: translateY(0) } to { transform: translateY(-14px) } }
        @media (prefers-reduced-motion: reduce) { .gdm-orb { animation: none !important } }
        .gdm-orb { animation: gdmDrift 9s ease-in-out infinite alternate; }
      `}</style>

      {/* ── Header ── */}
      <header style={{ background: NAVY, borderBottom: '1px solid rgba(255,255,255,0.10)' }}>
        <div style={{ ...wrap, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      gap: '1rem', paddingTop: '0.85rem', paddingBottom: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <img src="/gdm-globe.png" alt="" aria-hidden="true"
                 style={{ width: 30, height: 30, borderRadius: '50%' }} />
            <span style={{ color: '#fff', fontWeight: 700, letterSpacing: '-0.01em', fontSize: '0.98rem' }}>
              Compliance Intelligence <span style={{ color: MIST, fontWeight: 500 }}>Platform</span>
            </span>
          </div>
          <Btn variant="ghost" onClick={goSignIn}>Sign in</Btn>
        </div>
      </header>

      {/* ── Hero: the globe is the one bold flourish ── */}
      <section style={{
        position: 'relative', background: `linear-gradient(135deg, ${NAVY} 0%, ${STEEL} 100%)`,
        color: '#fff', overflow: 'hidden',
      }}>
        {/* Soft luminous halo, sized to the orb and sitting behind it. */}
        <div aria-hidden="true" style={{
          position: 'absolute', right: '-8%', top: '-18%', width: 'min(760px, 92vw)',
          height: 'min(760px, 92vw)', pointerEvents: 'none',
          background: 'radial-gradient(circle at 50% 50%, rgba(214,228,240,0.30) 0%, rgba(214,228,240,0.10) 42%, rgba(27,58,92,0) 68%)',
        }} />
        <img className="gdm-orb" src="/gdm-globe.png" alt="" aria-hidden="true" style={{
          position: 'absolute', right: '-10%', top: '-6%', width: 'min(620px, 78vw)',
          height: 'auto', opacity: 0.9, pointerEvents: 'none',
          filter: 'drop-shadow(0 0 70px rgba(160,200,235,0.42)) drop-shadow(0 26px 60px rgba(0,0,0,0.36))',
        }} />

        <div style={{ ...wrap, position: 'relative', paddingTop: 'clamp(3.5rem, 9vw, 7rem)',
                      paddingBottom: 'clamp(3.5rem, 9vw, 7rem)' }}>
          <div style={{ maxWidth: 640 }}>
            <p style={{ fontFamily: MONO, fontSize: 'clamp(0.85rem, 1.5vw, 1rem)', color: MIST,
                        margin: '0 0 1.5rem', maxWidth: '52ch', lineHeight: 1.6 }}>
              What if you knew you were compliant — before Dubai Municipality did?
            </p>
            <h1 style={{ fontSize: 'clamp(2.4rem, 5.6vw, 4rem)', lineHeight: 1.03, fontWeight: 800,
                         letterSpacing: '-0.035em', margin: '0 0 1rem', textWrap: 'balance' }}>
              Compliance Intelligence Platform
            </h1>
            <p style={{ fontFamily: MONO, fontSize: 'clamp(0.95rem, 1.8vw, 1.15rem)',
                        margin: '0 0 1.6rem', letterSpacing: '-0.01em' }}>
              Every certificate. Every asset. <strong style={{ color: MIST }}>Before submission.</strong>
            </p>
            <p style={{ color: 'rgba(255,255,255,0.80)', maxWidth: '46ch', margin: '0 0 2rem', lineHeight: 1.65 }}>
              Laboratory results are read, checked against the guideline they cite, and confirmed
              by a person — before the report leaves your office.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.7rem' }}>
              <Btn variant="light" onClick={() => document.getElementById('how')?.scrollIntoView({ behavior: 'smooth' })}>
                See how it works
              </Btn>
              <Btn variant="ghost" onClick={goSignIn}>Sign in</Btn>
            </div>
          </div>
        </div>
      </section>

      {/* ── The problem ── */}
      <section id="problem" style={{ padding: 'clamp(3.5rem, 8vw, 6rem) 0', background: '#fff' }}>
        <div style={wrap}>
          <p style={{ ...eyebrow, color: STEEL }}>The problem</p>
          <h2 style={{ fontSize: 'clamp(1.7rem, 3.6vw, 2.5rem)', lineHeight: 1.12, fontWeight: 800,
                       letterSpacing: '-0.025em', color: INK, margin: '0 0 0.9rem', textWrap: 'balance' }}>
            “Hopefully there’s nothing wrong.”
          </h2>
          <p style={{ fontSize: '1.05rem', color: SLATE, maxWidth: '64ch', lineHeight: 1.7, margin: 0 }}>
            That sentence is the whole risk. The laboratory tests. Dubai Municipality assesses.
            Everything between those two events is a person reading a PDF and forming an opinion —
            and the first sign of a problem arrives weeks later, in writing, from the regulator.
          </p>
          <div style={{ display: 'grid', gap: '1.1rem', marginTop: '2.2rem',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(255px, 1fr))' }}>
            <Card k="Today" title="Read by eye">
              Someone checks the numbers against limits they have to remember, on a document they cannot search.
            </Card>
            <Card k="Today" title="Filed on trust">
              If nothing looks obviously wrong, the report is forwarded. Nothing records what was checked, or by whom.
            </Card>
            <Card k="Today" title="Answered late">
              A query from DM is the first confirmation that something was missed — long after the sample was taken.
            </Card>
          </div>
        </div>
      </section>

      {/* ── What it catches ── */}
      <section id="catches" style={{ padding: 'clamp(3.5rem, 8vw, 6rem) 0', background: NAVY, color: '#fff' }}>
        <div style={wrap}>
          <p style={{ ...eyebrow, color: MIST }}>What it catches</p>
          <h2 style={{ fontSize: 'clamp(1.7rem, 3.6vw, 2.5rem)', lineHeight: 1.12, fontWeight: 800,
                       letterSpacing: '-0.025em', margin: '0 0 0.9rem', textWrap: 'balance' }}>
            The things a careful reader misses
          </h2>
          <p style={{ color: 'rgba(255,255,255,0.78)', maxWidth: '60ch', margin: '0 0 2rem', lineHeight: 1.7 }}>
            Not a summary of the certificate. A check of it — against the guideline it names.
          </p>

          {[
            {
              tag: 'UNASSESSED', title: 'Silence is not a pass',
              body: 'A chemistry certificate prints detection limits but no compliance limits, so twenty-three parameters cannot be judged from it at all. They are reported as unassessed — never folded into a green tick.',
            },
            {
              tag: 'SUPERSEDED', title: 'A citation that has quietly expired',
              body: 'Certificates sampled in 2026 still cite the 2024 edition of the Legionella guideline. The limits are unchanged, so the result stands — but the citation does not, and the regulator is entitled to ask.',
              quote: 'cites DM-HSD-GU44-LCWS2 edition 2024 — V.6 was issued 2025-08-19',
            },
            {
              tag: 'SCOPE', title: 'The right limits for the right asset',
              body: 'pH and turbidity appear in two different specifications. A tank is judged as a tank and a lagoon as a lagoon — never by whichever name happened to match.',
            },
          ].map((c, i, arr) => (
            <div key={c.tag} style={{
              display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '1rem 1.15rem',
              alignItems: 'start', padding: '1.35rem 0',
              borderBottom: i === arr.length - 1 ? 'none' : '1px solid rgba(255,255,255,0.14)',
            }}>
              <span style={{ fontFamily: MONO, fontSize: '0.7rem', letterSpacing: '0.08em', color: MIST,
                             border: '1px solid rgba(214,228,240,0.45)', borderRadius: 4,
                             padding: '0.2rem 0.45rem', whiteSpace: 'nowrap' }}>{c.tag}</span>
              <div>
                <h3 style={{ margin: '0 0 0.35rem', fontSize: '1.02rem', fontWeight: 700 }}>{c.title}</h3>
                <p style={{ margin: 0, color: 'rgba(255,255,255,0.78)', fontSize: '0.93rem', lineHeight: 1.65 }}>{c.body}</p>
                {c.quote && (
                  <p style={{ fontFamily: MONO, fontSize: '0.8rem', color: MIST, margin: '0.7rem 0 0',
                              borderLeft: `2px solid ${MIST}`, padding: '0.4rem 0 0.4rem 0.85rem' }}>{c.quote}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Specimen certificate ── */}
      <section id="certificate" style={{ padding: 'clamp(3.5rem, 8vw, 6rem) 0', background: SURFACE }}>
        <div style={{ ...wrap, display: 'grid', gap: 'clamp(2rem, 5vw, 3.5rem)',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', alignItems: 'center' }}>
          <div>
            <p style={{ ...eyebrow, color: STEEL }}>A certificate, checked</p>
            <h2 style={{ fontSize: 'clamp(1.6rem, 3.2vw, 2.2rem)', lineHeight: 1.14, fontWeight: 800,
                         letterSpacing: '-0.025em', color: INK, margin: '0 0 0.9rem', textWrap: 'balance' }}>
              The verdict, and what it rests on
            </h2>
            <p style={{ color: SLATE, lineHeight: 1.7, margin: 0, maxWidth: '46ch' }}>
              Every result is shown exactly as the laboratory printed it, beside the limit it was
              judged against and the guideline that limit came from. Nothing is rounded, rewritten
              or inferred.
            </p>
          </div>

          <figure style={{ margin: 0, background: '#fff', border: `1px solid ${BORDER}`,
                           borderRadius: 10, overflow: 'hidden', boxShadow: '0 12px 34px rgba(11,18,64,0.10)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem',
                          padding: '0.8rem 1.05rem', borderBottom: `1px solid ${BORDER}`, background: SURFACE }}>
              <span style={{ fontFamily: MONO, fontSize: '0.7rem', color: SLATE, letterSpacing: '0.05em' }}>
                WD-R-260421-0222 · MICROBIOLOGY
              </span>
              <span style={{ fontFamily: MONO, fontSize: '0.7rem', color: SLATE, letterSpacing: '0.05em' }}>
                WIMPEY LABORATORIES
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.95rem 1.05rem',
                          borderBottom: `1px solid ${BORDER}` }}>
              <span aria-hidden="true" style={{ width: 9, height: 9, borderRadius: '50%', background: PASS }} />
              <strong style={{ color: INK, fontSize: '1.02rem', letterSpacing: '-0.02em' }}>Compliant</strong>
              <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: '0.72rem', color: SLATE }}>
                7 of 7 assessed
              </span>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: MONO,
                              fontSize: '0.755rem', fontVariantNumeric: 'tabular-nums' }}>
                <thead>
                  <tr>
                    {['Parameter', 'Result', 'Limit', 'Status'].map((h, i) => (
                      <th key={h} scope="col" style={{
                        textAlign: i === 0 ? 'left' : 'right', padding: '0.5rem 1.05rem',
                        fontSize: '0.66rem', letterSpacing: '0.1em', textTransform: 'uppercase',
                        color: SLATE, fontWeight: 600, borderBottom: `1px solid ${BORDER}`,
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Escherichia coli', '<1', 'Zero'],
                    ['Enterococci', '<1', 'Zero'],
                    ['Total Coliforms', '<1', 'Zero'],
                    ['Total Bacterial Count', '<1', '500'],
                    ['Pseudomonas aeruginosa', '<1', 'Zero'],
                  ].map(([p, r, l]) => (
                    <tr key={p}>
                      <td style={{ padding: '0.48rem 1.05rem', borderBottom: `1px solid ${BORDER}`, color: '#374151' }}>{p}</td>
                      <td style={{ padding: '0.48rem 1.05rem', borderBottom: `1px solid ${BORDER}`, textAlign: 'right', color: '#374151' }}>{r}</td>
                      <td style={{ padding: '0.48rem 1.05rem', borderBottom: `1px solid ${BORDER}`, textAlign: 'right', color: '#374151' }}>{l}</td>
                      <td style={{ padding: '0.48rem 1.05rem', borderBottom: `1px solid ${BORDER}`, textAlign: 'right' }}>
                        <span style={{ fontSize: '0.66rem', letterSpacing: '0.05em', color: PASS,
                                       border: `1px solid ${PASS}`, borderRadius: 3, padding: '0.08rem 0.38rem' }}>PASS</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <figcaption style={{ padding: '0.75rem 1.05rem', fontFamily: MONO, fontSize: '0.68rem',
                                 color: SLATE, display: 'flex', justifyContent: 'space-between',
                                 gap: '1rem', flexWrap: 'wrap' }}>
              <span>ASSESSED AGAINST DM-HSD-GU44-LCWS2</span>
              <span>GATE No.2 — GRP WATER TANK</span>
            </figcaption>
          </figure>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how" style={{ padding: 'clamp(3.5rem, 8vw, 6rem) 0', background: '#fff' }}>
        <div style={wrap}>
          <p style={{ ...eyebrow, color: STEEL }}>How it works</p>
          <h2 style={{ fontSize: 'clamp(1.7rem, 3.6vw, 2.5rem)', lineHeight: 1.12, fontWeight: 800,
                       letterSpacing: '-0.025em', color: INK, margin: '0 0 0.4rem', textWrap: 'balance' }}>
            Five steps, and a record of every one
          </h2>
          <ol style={{ listStyle: 'none', margin: '2rem 0 0', padding: 0, borderTop: `1px solid ${BORDER}` }}>
            {[
              ['CONFIGURE', 'Your sites and their assets.', 'Tanks, water bodies, fountains, outlets — each one carrying the specification that governs it.'],
              ['UPLOAD', 'The certificate as issued.', 'Values are read from the document itself, not retyped, and kept exactly as printed.'],
              ['CONFIRM', 'A person approves it.', 'Nothing enters the compliance record unreviewed. Saving is the act of confirming.'],
              ['REPORT', 'Submission-ready.', 'Verdicts, the standard applied, and the certificate behind them — assembled for Dubai Municipality.'],
              ['OVERSEE', 'Across the portfolio.', 'What passed, what failed, what nobody has assessed yet, and what is still awaiting review.'],
            ].map(([k, t, d]) => (
              <li key={k} style={{ display: 'grid', gridTemplateColumns: '7.5rem 1fr', gap: '1.1rem',
                                   padding: '1.05rem 0', borderBottom: `1px solid ${BORDER}`, alignItems: 'baseline' }}>
                <span style={{ fontFamily: MONO, fontSize: '0.71rem', letterSpacing: '0.1em', color: STEEL }}>{k}</span>
                <span style={{ fontSize: '0.95rem', color: SLATE, lineHeight: 1.65 }}>
                  <strong style={{ color: INK, fontWeight: 700 }}>{t}</strong> {d}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ── Close ── */}
      <section style={{ padding: 'clamp(3.5rem, 8vw, 5.5rem) 0',
                        background: `linear-gradient(135deg, ${NAVY} 0%, ${STEEL} 100%)`, color: '#fff' }}>
        <div style={wrap}>
          <p style={{ ...eyebrow, color: MIST }}>Assurance, not storage</p>
          <h2 style={{ fontSize: 'clamp(1.7rem, 3.6vw, 2.4rem)', lineHeight: 1.12, fontWeight: 800,
                       letterSpacing: '-0.025em', margin: '0 0 0.9rem', maxWidth: '20ch' }}>
            Know before you submit.
          </h2>
          <p style={{ color: 'rgba(255,255,255,0.80)', maxWidth: '58ch', margin: '0 0 1.8rem', lineHeight: 1.7 }}>
            The laboratory already tests. The regulator already assesses. This is the part in
            between — done deliberately, and written down.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.7rem' }}>
            <Btn variant="light" onClick={goSignIn}>Sign in</Btn>
            <Btn variant="ghost" onClick={goSignIn}>Request access</Btn>
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  )
}
