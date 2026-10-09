import ArchitectureDiagram from './ArchitectureDiagram'

const stats = [
  { value: '1m', label: 'event study equity bars' },
  { value: '60s', label: 'default study entry delay' },
  { value: '30bp', label: 'default round trip cost' },
  { value: '2h', label: 'hypothetical study horizon' },
]

export default function ArchitectureSection() {
  return (
    <section
      style={{ background: '#0d0d0d', padding: '128px 0' }}
    >
      <div className="container">
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--neon)',
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            marginBottom: '48px',
          }}
        >
          02 // ARCHITECTURE
        </div>

        <h2
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 'clamp(32px, 4vw, 48px)',
            color: 'var(--text-primary)',
            fontWeight: 400,
            marginBottom: '64px',
          }}
        >
          How it works.
        </h2>

        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            padding: '32px',
            marginBottom: '64px',
            overflowX: 'auto',
          }}
        >
          <ArchitectureDiagram />
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '48px',
          }}
          className="stats-grid"
        >
          {stats.map((s) => (
            <div key={s.label}>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '32px',
                  color: 'var(--neon)',
                  lineHeight: 1,
                  marginBottom: '8px',
                }}
              >
                {s.value}
              </div>
              <div
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                }}
              >
                {s.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        @media (max-width: 1024px) {
          .stats-grid {
            grid-template-columns: repeat(2, 1fr) !important;
          }
        }
        @media (max-width: 640px) {
          .stats-grid {
            grid-template-columns: 1fr 1fr !important;
          }
        }
      `}</style>
    </section>
  )
}
