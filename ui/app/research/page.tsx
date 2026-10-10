'use client'

import { useState, type ChangeEvent } from 'react'
import Header from '@/components/Header'

type Summary = {
  events: number
  signals: number
  priced: number
  missing_prediction_contracts: number
  missing_equity_contracts: number
  mean_net_bps: number | null
}

type Study = {
  assumptions: { price_model?: string; round_trip_cost_bps?: number }
  train: Summary
  holdout: Summary
  event_results: Array<{ event_id: string; split: string; priced_contracts: number; mean_net_bps: number | null }>
}

type Audit = {
  ready_for_study: boolean
  global_issues: string[]
  events: Array<{ event_id: string; equity_coverage_pct: number; issues: string[] }>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isSummary(value: unknown): value is Summary {
  if (!isRecord(value)) return false
  return ['events', 'signals', 'priced', 'missing_prediction_contracts', 'missing_equity_contracts']
    .every((key) => typeof value[key] === 'number') &&
    (value.mean_net_bps === null || typeof value.mean_net_bps === 'number')
}

function isStudy(value: unknown): value is Study {
  return isRecord(value) && isRecord(value.assumptions) && isSummary(value.train) &&
    isSummary(value.holdout) && Array.isArray(value.event_results) &&
    value.event_results.every((item: unknown) => isRecord(item) &&
      typeof item.event_id === 'string' && typeof item.split === 'string' &&
      typeof item.priced_contracts === 'number' &&
      (item.mean_net_bps === null || typeof item.mean_net_bps === 'number'))
}

function isAudit(value: unknown): value is Audit {
  return isRecord(value) && typeof value.ready_for_study === 'boolean' &&
    Array.isArray(value.global_issues) && value.global_issues.every((item: unknown) => typeof item === 'string') &&
    Array.isArray(value.events) && value.events.every((item: unknown) => isRecord(item) &&
      typeof item.event_id === 'string' && typeof item.equity_coverage_pct === 'number' &&
      Array.isArray(item.issues) && item.issues.every((issue: unknown) => typeof issue === 'string'))
}

function formatBps(value: number | null): string {
  return value === null ? 'No priced events' : `${value.toFixed(1)} bps`
}

export default function ResearchPage() {
  const [study, setStudy] = useState<Study | null>(null)
  const [audit, setAudit] = useState<Audit | null>(null)
  const [error, setError] = useState('')

  async function readFile(event: ChangeEvent<HTMLInputElement>, kind: 'study' | 'audit') {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      if (file.size > 5_000_000) throw new Error('Choose a JSON file under 5 MB.')
      const parsed: unknown = JSON.parse(await file.text())
      if (kind === 'study') {
        if (!isStudy(parsed)) throw new Error('This is not an event study report.')
        setStudy(parsed)
      } else {
        if (!isAudit(parsed)) throw new Error('This is not a coverage audit report.')
        setAudit(parsed)
      }
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not read this JSON file.')
    }
  }

  return (
    <>
      <Header />
      <main className="research-page container">
        <p className="research-kicker">RESEARCH / LOCAL REPORT VIEWER</p>
        <h1>Evidence before execution.</h1>
        <p className="research-intro">Load the coverage audit and event study JSON files produced by the Python research tools. Files stay in this browser tab and are not uploaded to the site.</p>
        <div className="research-upload-grid">
          <label className="research-upload">Coverage audit JSON<input type="file" accept=".json,application/json" onChange={(event) => readFile(event, 'audit')} /></label>
          <label className="research-upload">Event study JSON<input type="file" accept=".json,application/json" onChange={(event) => readFile(event, 'study')} /></label>
        </div>
        {error && <p className="research-error" role="alert">{error}</p>}

        <section className="research-section" aria-labelledby="coverage-heading">
          <h2 id="coverage-heading">Data coverage</h2>
          {!audit ? <p className="research-empty">Load a coverage audit to inspect provenance and missing data.</p> : <>
            <p className={audit.ready_for_study ? 'research-good' : 'research-error'}>
              {audit.ready_for_study ? 'CSV checks passed' : 'CSV checks need attention'} · {audit.events.length} manifest rows
            </p>
            {audit.global_issues.length > 0 && <p>Global issues: {audit.global_issues.join(', ')}</p>}
            <div className="research-rows">{audit.events.map((row, index) => <div className="research-row" key={`${row.event_id}-${index}`}>
              <strong>{row.event_id}</strong><span>{row.equity_coverage_pct.toFixed(1)}% equity minutes</span>
              <span>{row.issues.length ? row.issues.join(', ') : 'No mechanical gaps'}</span>
            </div>)}</div>
          </>}
        </section>

        <section className="research-section" aria-labelledby="study-heading">
          <h2 id="study-heading">Event study</h2>
          {!study ? <p className="research-empty">Load an event study report to compare training and later holdout releases.</p> : <>
            <p className="research-assumptions">Price model: {study.assumptions.price_model ?? 'bar_open'} · Additional costs: {study.assumptions.round_trip_cost_bps ?? 'unknown'} bps</p>
            <div className="research-summary-grid">{(['train', 'holdout'] as const).map((split) => {
              const row = study[split]
              return <div className="research-summary" key={split}>
                <h3>{split === 'train' ? 'Training' : 'Later holdout'}</h3>
                <strong>{formatBps(row.mean_net_bps)}</strong>
                <p>{row.events} releases · {row.signals} signal releases · {row.priced} priced releases</p>
                <p>{row.missing_prediction_contracts} missing prediction rows · {row.missing_equity_contracts} missing equity rows</p>
              </div>
            })}</div>
            <div className="research-rows">{study.event_results.map((row, index) => <div className="research-row" key={`${row.event_id}-${index}`}>
              <strong>{row.event_id}</strong><span>{row.split}</span><span>{row.priced_contracts} priced contracts · {formatBps(row.mean_net_bps)}</span>
            </div>)}</div>
          </>}
        </section>
        <p className="research-caveat">These are research estimates. Coverage checks do not verify provider availability times, and backtest returns do not establish a tradable edge. Live execution remains disabled.</p>
      </main>
    </>
  )
}
