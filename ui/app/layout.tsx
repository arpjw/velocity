import type { Metadata } from 'next'
import '@fontsource/dm-serif-display/latin-400.css'
import '@fontsource/dm-sans/latin-400.css'
import '@fontsource/dm-sans/latin-500.css'
import '@fontsource/dm-mono/latin-300.css'
import '@fontsource/dm-mono/latin-400.css'
import '@fontsource/dm-mono/latin-500.css'
import './globals.css'

export const metadata: Metadata = {
  title: 'Robinhood Velocity Signal Engine',
  description:
    'Research on whether prediction market repricing leads related equity moves. Shadow mode only.',
  openGraph: {
    title: 'Robinhood Velocity Signal Engine',
    description:
      'Research on whether prediction market repricing leads related equity moves. Shadow mode only.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
