'use client'

import { useEffect, useState } from 'react'

interface MarketRow {
  ticker: string
  lastPrice: number
  volume: number
}

export default function TerminalWidget() {
  const [markets, setMarkets] = useState<MarketRow[]>([])
  const [status, setStatus] = useState<'loading' | 'available' | 'unavailable'>('loading')
  const [fetchedAt, setFetchedAt] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    async function fetchMarkets() {
      try {
        const response = await fetch('/api/markets', { cache: 'no-store' })
        if (!response.ok) throw new Error('Market feed unavailable')
        const data: { markets: MarketRow[]; fetchedAt: string } = await response.json()
        if (!active) return
        setMarkets(data.markets)
        setFetchedAt(data.fetchedAt)
        setStatus('available')
      } catch {
        if (active) setStatus('unavailable')
      }
    }

    fetchMarkets()
    const interval = setInterval(fetchMarkets, 30000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', overflow: 'hidden' }}>
      <div style={{ padding: '12px 20px', background: 'var(--surface-elevated)', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-secondary)' }}>KALSHI // FED MARKETS</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: status === 'available' ? 'var(--neon)' : 'var(--text-tertiary)' }}>
          {status === 'available' ? 'PUBLIC DATA' : status.toUpperCase()}
        </span>
      </div>

      <div style={{ padding: '20px' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-tertiary)', letterSpacing: '0.1em', marginBottom: '12px' }}>
          RECENTLY TRADED CONTRACTS // LAST TRADE
        </div>
        {markets.length > 0 ? markets.map((market) => (
          <div key={market.ticker} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', padding: '12px 0', borderBottom: '1px solid var(--surface-elevated)' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{market.ticker}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '4px' }}>VOLUME {market.volume.toLocaleString()}</div>
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '16px', color: 'var(--neon)', flexShrink: 0 }}>{(market.lastPrice * 100).toFixed(1)}%</div>
          </div>
        )) : (
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
            {status === 'loading' ? 'Loading public market data…' : status === 'unavailable' ? 'Public market data is unavailable right now.' : 'No traded contracts returned.'}
          </p>
        )}
        <p style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-tertiary)', lineHeight: 1.5, marginTop: '16px' }}>
          Last trade is not a live bid or ask. {fetchedAt ? `Feed checked ${new Date(fetchedAt).toLocaleTimeString()}.` : ''}
        </p>
      </div>

      <div style={{ padding: '10px 20px', borderTop: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-tertiary)' }}>
        RESEARCH MODE // NO ORDERS OR PERFORMANCE CLAIMS
      </div>
    </div>
  )
}
