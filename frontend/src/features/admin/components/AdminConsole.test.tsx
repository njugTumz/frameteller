import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AdminConsole } from './AdminConsole'

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
