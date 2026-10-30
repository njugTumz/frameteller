import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { UndoToast } from './UndoToast'

describe('UndoToast', () => {
  it('says what was removed and takes it back', () => {
    const onUndo = vi.fn()
    render(<UndoToast pending={{ kind: 'beat', id: 'rec-1', label: 'Beat 2' }} onUndo={onUndo} />)
    expect(screen.getByRole('status').textContent).toBe('Beat 2 removed. Its words and voice leave the animatic.Undo')
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(onUndo).toHaveBeenCalled()
  })

  it('shows nothing when nothing is pending', () => {
    const { container } = render(<UndoToast pending={null} onUndo={vi.fn()} />)
    expect(container.innerHTML).toBe('')
  })
})
