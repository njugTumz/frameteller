import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { JudgePasses } from './JudgePasses'

const reserve = { calendar_usd: 25, override_usd: null, stories_per_pass_per_day: 15 }
const passes = [{ pass_id: 'a1b2c3d4e5f6a7b8', first_seen: '2026-11-05T09:00:00+00:00', stories_today: 3, spent_today_usd: 0.42 }]

describe('JudgePasses', () => {
  it('lists each pass with its stories and spend today', () => {
    render(<JudgePasses reserve={reserve} passes={passes} onReserve={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Judge passes today (1)' })).toBeTruthy()
    const row = screen.getByRole('row', { name: /a1b2c3d4e5f6a7b8/ })
    expect(row.textContent).toContain('3')
    expect(row.textContent).toContain('$0.42')
    expect(screen.getByText(/Reserve \$25\.00 a day from the calendar\. Each pass may start 15 stories a day\./)).toBeTruthy()
  })

  it('lowers the reserve, and offers to go back to the calendar once lowered', () => {
    const onReserve = vi.fn()
    const { rerender } = render(<JudgePasses reserve={reserve} passes={[]} onReserve={onReserve} />)
    expect(screen.getByText('No judge has started a story today.')).toBeTruthy()
    const lower = screen.getByRole('button', { name: 'Lower now' })
    expect(lower).toHaveProperty('disabled', true)
    fireEvent.change(screen.getByLabelText("Lower the judges' reserve to (USD a day)"), { target: { value: '5' } })
    fireEvent.click(lower)
    expect(onReserve).toHaveBeenCalledWith(5)
    rerender(<JudgePasses reserve={{ ...reserve, override_usd: 5 }} passes={[]} onReserve={onReserve} />)
    expect(screen.getByText(/lowered here to \$5\.00/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Back to the calendar' }))
    expect(onReserve).toHaveBeenLastCalledWith(null)
  })
})
