const steps = [
  { title: 'Market data', detail: 'Kalshi + Polymarket' },
  { title: 'Observations', detail: 'Timestamped quotes' },
  { title: 'Shadow signals', detail: 'Candidates, no orders' },
  { title: 'Event study', detail: 'Delayed equity entry' },
]

export default function ArchitectureDiagram() {
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', gap: '12px', minWidth: '650px' }}>
      {steps.map((step, index) => (
        <div key={step.title} style={{ display: 'flex', alignItems: 'center', flex: 1, gap: '12px' }}>
          <div style={{ flex: 1, border: '1px solid var(--border)', borderRadius: '4px', padding: '18px 12px', minHeight: '90px' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--neon)', marginBottom: '8px' }}>{step.title}</div>
            <div style={{ fontFamily: 'var(--font-sans)', fontSize: '12px', color: 'var(--text-secondary)' }}>{step.detail}</div>
          </div>
          {index < steps.length - 1 && <span aria-hidden="true" style={{ color: 'var(--text-tertiary)', fontSize: '18px' }}>→</span>}
        </div>
      ))}
    </div>
  )
}
