import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Errors } from '../api'
import { ErrorsTab } from './ErrorsTab'

const errors: Errors = {
  recent: [
    { at: '2026-10-30T09:00:00+00:00', component: 'api', code: 'invalid_request', message: 'POST /projects: body.style: Input should be …', project_id: null, visitor: 'a1b2c3d4e5f6' },
    { at: '2026-10-30T08:00:00+00:00', component: 'image', code: 'model_unavailable', message: 'Muse Image is not answering.', project_id: 'p1', visitor: null },
  ],
  counts_24h: { invalid_request: 1, model_unavailable: 1 },
  health: [{ model: 'muse-image-1.0', calls: 12, failures: 1, retries: 2, p95_ms: 18400 }],
  failed_jobs: [
    { key: 'generate_panel:p1:s1:r1', kind: 'generate_panel', component: 'image', code: 'model_unavailable', message: 'Muse Image is not answering.', at: '2026-10-30T08:00:00+00:00', project_id: 'p1', retries: 1 },
  ],
  reports: [{ id: 'r1', at: '2026-10-30T09:30:00+00:00', project_id: 'p1', text: 'The cat vanished in shot 2.', visitor: 'a1b2c3d4e5f6' }],
}

describe('ErrorsTab', () => {
  it('shows recent errors, counts, model health, failed jobs and reports', () => {
    render(<ErrorsTab errors={errors} onRetry={vi.fn()} />)
    const rows = screen.getAllByTestId('incident')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.textContent).toContain('invalid_request')
    expect(rows[0]?.textContent).toContain('a1b2c3d4e5f6')
    expect(within(screen.getByRole('region', { name: 'Last 24 hours' })).getByText('invalid_request')).toBeTruthy()
    const model = screen.getByRole('row', { name: /muse-image-1\.0/ })
    expect(model.textContent).toContain('12')
    expect(model.textContent).toContain('18.4s')
    expect(screen.getByText('The cat vanished in shot 2.')).toBeTruthy()
    expect(screen.getByText(/retried 1×/)).toBeTruthy()
  })

  it('calls a voice session\'s p95 its session length, not latency, and gives each column its own cell', () => {
    const voice = { model: 'muse-voice-transcribe-1.0', calls: 3, failures: 0, retries: 0, p95_ms: 137100 }
    render(<ErrorsTab errors={{ ...errors, health: [...errors.health, voice] }} onRetry={vi.fn()} />)
    expect(screen.getByRole('row', { name: /muse-voice-transcribe/ }).textContent).toContain('137.1s session length')
    expect(screen.getByRole('row', { name: /muse-image-1\.0/ }).textContent).toContain('18.4s latency')
    const [first] = screen.getAllByTestId('incident')
    const cells = within(first as HTMLElement).getAllByRole('cell')
    expect(cells.map((c) => c.className.includes('px-2'))).toEqual([true, true, true, true, true, true])
    expect(cells[2]?.className).toContain('break-words') // a long message wraps in its own column
  })

  it('retries a failed job by its key', () => {
    const onRetry = vi.fn()
    render(<ErrorsTab errors={errors} onRetry={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: 'Retry generate_panel:p1:s1:r1' }))
    expect(onRetry).toHaveBeenCalledWith('generate_panel:p1:s1:r1')
  })

  it('says when all is quiet', () => {
    render(<ErrorsTab errors={{ recent: [], counts_24h: {}, health: [], failed_jobs: [], reports: [] }} onRetry={vi.fn()} />)
    expect(screen.getByText('No errors in the last 24 hours.')).toBeTruthy()
    expect(screen.getByText('No model calls yet today.')).toBeTruthy()
  })
})
