import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { JudgeWelcome } from './JudgeWelcome'

describe('JudgeWelcome', () => {
  it('says judge access is on and offers the tour first, then a story', () => {
    const onStart = vi.fn()
    const onTour = vi.fn()
    render(<JudgeWelcome state={{ kind: 'ok', until: '2026-11-19T12:00:00+00:00' }} onStart={onStart} onTour={onTour} />)
    screen.getByText(/Judge access is on in this browser/)
    const [first, second] = screen.getAllByRole('button')
    expect(first?.textContent).toBe('Take the 2-minute tour')
    expect(second?.textContent).toBe('Start a story')
    screen.getByRole('button', { name: 'Take the 2-minute tour' }).click()
    expect(onTour).toHaveBeenCalled()
    screen.getByRole('button', { name: 'Start a story' }).click()
    expect(onStart).toHaveBeenCalled()
  })

  it('explains a link that did not work', () => {
    render(<JudgeWelcome state={{ kind: 'failed', message: 'That judge link is not valid any more.' }} onStart={vi.fn()} onTour={vi.fn()} />)
    expect(screen.getByRole('alert').textContent).toContain('not valid any more')
  })
})
