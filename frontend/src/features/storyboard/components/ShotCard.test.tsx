import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { shot } from '../../../test/builders'
import { ShotCard } from './ShotCard'

describe('ShotCard', () => {
  it('deletes the shot with one click (Undo follows), and only when offered', () => {
    const onDelete = vi.fn()
    const props = { shot: shot(3), phase: { kind: 'not-drawn' as const }, imageSrc: null, names: ['Wren'], onOpen: vi.fn(), onRetry: vi.fn() }
    const { rerender } = render(<ShotCard {...props} onDelete={onDelete} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete shot 3' }))
    expect(onDelete).toHaveBeenCalledTimes(1)
    rerender(<ShotCard {...props} />)
    expect(screen.queryByRole('button', { name: /Delete shot/ })).toBeNull()
  })
})
