const cards = [
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
        <polyline
          points="12,6 12,12 16,14"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    ),
    title: 'An open question.',
    titleFont: 'serif' as const,
    body: 'A fast change in a contract price might lead a related equity, or both markets might react to the same announcement. The event study measures which moved first.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <path
          d="M4 20 L12 4 L20 20"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <line
          x1="7"
          y1="14"
          x2="17"
          y2="14"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    ),
    title: 'Measure velocity.',
    titleFont: 'mono' as const,
    body: 'The research pipeline evaluates a price change and traded volume using only observations available at the time. Thresholds are tested for sensitivity, not treated as proof of information.',
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="13" r="9" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M12 9 L12 13"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <path
          d="M12 13 L15 13"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <path
          d="M9 2 L15 2"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    ),
    title: 'Account for costs.',
    titleFont: 'serif' as const,
    body: 'A hypothetical two-hour horizon includes delayed entry and transaction costs. Results are compared with prerelease moves, public news direction, and a chronological holdout.',
  },
]

export default function SignalSection() {
  return (
    <section id="signal" style={{ background: 'var(--bg)', padding: '128px 0' }}>
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
          01 // THE SIGNAL
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
          A hypothesis to measure.
        </h2>

        <div className="signal-grid">
          {cards.map((card) => (
            <div key={card.title} className="signal-card">
              <div style={{ color: 'var(--neon)', marginBottom: '20px' }}>{card.icon}</div>
              <h3
                style={{
                  fontFamily:
                    card.titleFont === 'mono' ? 'var(--font-mono)' : 'var(--font-serif)',
                  fontSize: '22px',
                  color: card.titleFont === 'mono' ? 'var(--neon)' : 'var(--text-primary)',
                  fontWeight: 400,
                  marginBottom: '16px',
                  lineHeight: 1.2,
                }}
              >
                {card.title}
              </h3>
              <p
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: '15px',
                  color: 'var(--text-secondary)',
                  lineHeight: 1.6,
                }}
              >
                {card.body}
              </p>
            </div>
          ))}
        </div>
      </div>

      <style>{`
        .signal-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 24px;
        }
        @media (max-width: 1024px) {
          .signal-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </section>
  )
}
