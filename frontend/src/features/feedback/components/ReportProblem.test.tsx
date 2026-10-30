import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ReportProblem } from './ReportProblem'

describe('ReportProblem', () => {
  it('opens a short form, counts to 500 and sends the words', () => {
    const onSend = vi.fn()
    render(<ReportProblem state="idle" error={null} onSend={onSend} onReset={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Report a problem' }))
    const box = screen.getByLabelText(/What went wrong\?/)
    expect(box).toHaveProperty('maxLength', 500)
    fireEvent.change(box, { target: { value: 'The cat vanished in shot 2.' } })
    expect(screen.getByText(/^27\/500/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
    expect(onSend).toHaveBeenCalledWith('The cat vanished in shot 2.')
  })

  it('sends without words, says thanks, and shows the limit when reached', () => {
    const onSend = vi.fn()
    const onReset = vi.fn()
    const { rerender } = render(<ReportProblem state="idle" error={null} onSend={onSend} onReset={onReset} />)
    fireEvent.click(screen.getByRole('button', { name: 'Report a problem' }))
    fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
    expect(onSend).toHaveBeenCalledWith('')

    rerender(<ReportProblem state="sending" error={null} onSend={onSend} onReset={onReset} />)
    expect(screen.getByRole('button', { name: 'Sending…' })).toHaveProperty('disabled', true)
    rerender(<ReportProblem state="sent" error={null} onSend={onSend} onReset={onReset} />)
    expect(screen.getByText('Thanks, we got your report.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onReset).toHaveBeenCalled()

    rerender(<ReportProblem state="idle" error="You've sent 5 reports today. Thank you; we'll look at them." onSend={onSend} onReset={onReset} />)
    fireEvent.click(screen.getByRole('button', { name: 'Report a problem' }))
    expect(screen.getByRole('alert').textContent).toContain("You've sent 5 reports today")
  })
})
