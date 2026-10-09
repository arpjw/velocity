const signalLayer = [
  { name: 'Kalshi REST + WebSocket', desc: 'Discovers active KXFED markets and records public prices with source and receipt times.' },
  { name: 'Polymarket CLOB', desc: 'Resolves outcome asset IDs before subscribing to market updates.' },
  { name: 'VelocityTracker', desc: 'Tracks configurable price-change windows and creates candidate signals.' },
  { name: 'Observation log', desc: 'Persists raw market observations for prospective analysis.' },
  { name: 'Point-in-time event study', desc: 'Aligns exact Fed contracts with minute equity bars, latency, costs, and holdout checks.' },
]

const executionLayer = [
  { name: 'Shadow mode', desc: 'Default mode records candidates without submitting any orders.' },
  { name: 'MockMCPClient', desc: 'Optional simulation path for exercising execution code. Mock fills are not market evidence.' },
  { name: 'Live order guard', desc: 'Order placement is blocked until verified fills and exits can be reconciled.' },
]

export default function StackSection() {
  return (
    <section style={{ background: 'var(--bg)', padding: '96px 0' }}>
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
          04 // STACK
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '64px',
          }}
          className="stack-grid"
        >
          <StackColumn title="Research pipeline" items={signalLayer} />
          <StackColumn title="Execution status" items={executionLayer} />
        </div>
      </div>

      <style>{`
        @media (max-width: 1024px) {
          .stack-grid {
            grid-template-columns: 1fr !important;
            gap: 48px !important;
          }
        }
      `}</style>
    </section>
  )
}

function StackColumn({
  title,
  items,
}: {
  title: string
  items: { name: string; desc: string }[]
}) {
  return (
    <div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          color: 'var(--text-tertiary)',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          marginBottom: '32px',
          paddingBottom: '12px',
          borderBottom: '1px solid var(--border)',
        }}
      >
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
        {items.map((item) => (
          <div key={item.name}>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '14px',
                color: 'var(--text-primary)',
                marginBottom: '4px',
              }}
            >
              {item.name}
            </div>
            <div
              style={{
                fontFamily: 'var(--font-sans)',
                fontSize: '13px',
                color: 'var(--text-secondary)',
                lineHeight: 1.5,
              }}
            >
              {item.desc}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
