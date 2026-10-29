import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { JudgeWelcome } from './JudgeWelcome'

describe('JudgeWelcome', () => {
  it('says judge access is on and starts a story', () => {
    const onStart = vi.fn()
    render(<JudgeWelcome state={{ kind: 'ok', until: '2026-11-19T12:00:00+00:00' }} onStart={onStart} />)
    screen.getByText(/Judge access is on in this browser/)
    screen.getByRole('button', { name: 'Start a story' }).click()
    expect(onStart).toHaveBeenCalled()
  })

  it('explains a link that did not work', () => {
    render(<JudgeWelcome state={{ kind: 'failed', message: 'That judge link is not valid any more.' }} onStart={vi.fn()} />)
    expect(screen.getByRole('alert').textContent).toContain('not valid any more')
  })
})
