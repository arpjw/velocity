import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

interface KalshiMarket {
  ticker?: string
  last_price_dollars?: string
  volume_fp?: string
}

function parseMarket(market: KalshiMarket) {
  const lastPrice = Number(market.last_price_dollars)
  const volume = Number(market.volume_fp)
  if (!market.ticker?.startsWith('KXFED-') || !Number.isFinite(lastPrice) || !Number.isFinite(volume)) return null
  if (lastPrice <= 0 || lastPrice >= 1 || volume <= 0) return null
  return { ticker: market.ticker, lastPrice, volume }
}

export async function GET() {
  try {
    const url = new URL('https://external-api.kalshi.com/trade-api/v2/markets')
    url.searchParams.set('series_ticker', 'KXFED')
    url.searchParams.set('status', 'open')
    url.searchParams.set('limit', '1000')
    const response = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(8000) })
    if (!response.ok) throw new Error(`Kalshi HTTP ${response.status}`)
    const data: { markets?: KalshiMarket[] } = await response.json()
    const markets = (data.markets ?? [])
      .map(parseMarket)
      .filter((market): market is NonNullable<typeof market> => market !== null)
      .sort((a, b) => b.volume - a.volume)
      .slice(0, 5)
    return NextResponse.json({ markets, fetchedAt: new Date().toISOString() })
  } catch {
    return NextResponse.json({ error: 'Market data unavailable' }, { status: 503 })
  }
}
