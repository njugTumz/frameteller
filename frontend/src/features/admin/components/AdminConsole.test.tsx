import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AdminConsole, JudgeGlimmerLine } from './AdminConsole'

const quiet = { recent: [], counts_24h: {}, health: [], failed_jobs: [], reports: [] }

describe('AdminConsole', () => {
  it('opens on the overview and switches to the Errors tab', () => {
    render(<AdminConsole overview={null} entries={[]} errors={quiet} error={null} onAct={vi.fn()} onWatch={vi.fn()} onReserve={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByRole('tab', { name: 'Overview' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByText('Needs a look (0)')).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: 'Errors (0)' }))
    expect(screen.getByText('No errors in the last 24 hours.')).toBeTruthy()
    expect(screen.queryByText('Needs a look (0)')).toBeNull()
  })
})

describe('JudgeGlimmerLine', () => {
  it("shows today's judge wake-ups, whether Glimmer is warm and the estimated Modal cost", () => {
    render(<JudgeGlimmerLine glimmer={{ day: '2026-10-31', wakes: 2, wakes_cap: 10, estimated_usd: 1.234, usd_cap: 5, warm: true, waking: false, last_cold_start_s: 187.4 }} />)
    expect(screen.getByTestId('judge-glimmer').textContent).toBe('Judge wake-ups today: 2 of 10 · Glimmer warm · last cold start 187 s · Modal today ≈ $1.23 of $5.00')
  })

  it('says when it is waking', () => {
    render(<JudgeGlimmerLine glimmer={{ day: '2026-10-31', wakes: 1, wakes_cap: 10, estimated_usd: 0.3, usd_cap: 5, warm: false, waking: true, last_cold_start_s: null }} />)
    expect(screen.getByTestId('judge-glimmer').textContent).toContain('Glimmer waking')
  })
})
