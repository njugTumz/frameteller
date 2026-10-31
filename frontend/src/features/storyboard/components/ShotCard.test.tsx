import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { shot } from '../../../test/builders'
import type { PanelPhase } from '../store'
import { ShotCard } from './ShotCard'

const READY: PanelPhase = { kind: 'ready', imageUrl: '/media/r2.webp', revision: 2, outdated: false }

function card(phase: PanelPhase, more: Partial<Parameters<typeof ShotCard>[0]> = {}) {
  const onRedraw = vi.fn()
  render(<ShotCard shot={shot(3)} phase={phase} imageSrc={phase.kind === 'ready' ? phase.imageUrl : null} names={['Wren']} onOpen={vi.fn()} onRedraw={onRedraw} {...more} />)
  return onRedraw
}

describe('ShotCard', () => {
  it('deletes the shot with one click (Undo follows), and only when offered', () => {
    const onDelete = vi.fn()
    const props = { shot: shot(3), phase: { kind: 'not-drawn' as const }, imageSrc: null, names: ['Wren'], onOpen: vi.fn(), onRedraw: vi.fn() }
    const { rerender } = render(<ShotCard {...props} onDelete={onDelete} />)
    fireEvent.click(screen.getByRole('button', { name: 'Delete shot 3' }))
    expect(onDelete).toHaveBeenCalledTimes(1)
    rerender(<ShotCard {...props} />)
    expect(screen.queryByRole('button', { name: /Delete shot/ })).toBeNull()
  })

  it('shows Redraw on every drawn panel, not only an outdated one', () => {
    card(READY)
    expect(screen.getByRole('button', { name: 'Redraw shot 3' }).textContent).toContain('Redraw')
  })

  it('asks what should change; it may stay empty, or be a Surprise me', () => {
    const onRedraw = card(READY)
    fireEvent.click(screen.getByRole('button', { name: 'Redraw shot 3' }))
    const box = screen.getByRole('textbox', { name: /What should change/ })
    expect(box.getAttribute('placeholder')).toEqual(expect.stringContaining('make it night'))
    fireEvent.change(box, { target: { value: ' make it night ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Redraw' }))
    expect(onRedraw).toHaveBeenLastCalledWith({ change: 'make it night', surprise: false })

    fireEvent.click(screen.getByRole('button', { name: 'Redraw shot 3' }))
    fireEvent.click(screen.getByRole('button', { name: 'Surprise me' }))
    expect(onRedraw).toHaveBeenLastCalledWith({ change: '', surprise: true })
  })

  it('keeps the previous drawing on screen while drawing, with how long it takes', () => {
    card({ kind: 'drawing', what: 'draft', previousUrl: '/media/r2.webp' }, { previousSrc: '/media/r2.webp' })
    expect(screen.getByRole('img', { name: /the drawing before/ }).getAttribute('src')).toEqual('/media/r2.webp')
    expect(screen.getByRole('status').textContent).toContain('Drawing… about 20 s')
    expect(screen.queryByRole('button', { name: 'Redraw shot 3' })).toBeNull()
  })

  it('offers Use new or Keep previous once the new drawing is in', () => {
    const onUseNew = vi.fn()
    const onKeepPrevious = vi.fn()
    card(READY, { choice: { previousSrc: '/media/r1.webp', busy: false, onUseNew, onKeepPrevious } })
    fireEvent.click(screen.getByRole('button', { name: 'Keep previous' }))
    fireEvent.click(screen.getByRole('button', { name: 'Use new' }))
    expect(onKeepPrevious).toHaveBeenCalledTimes(1)
    expect(onUseNew).toHaveBeenCalledTimes(1)
  })

  it('after a refusal says what to change and offers the suggested change, with the drawing kept', () => {
    const onRedraw = card(
      { kind: 'failed', message: 'Muse Image turned this frame down. Say plainly what happens.', previousUrl: '/media/r2.webp', suggestion: 'keep it calm and friendly: a fox on a roof' },
      { previousSrc: '/media/r2.webp' },
    )
    expect(screen.getByRole('alert').textContent).toContain('Say plainly what happens')
    expect(screen.getByRole('img', { name: /the drawing before/ })).toBeTruthy()
    expect((screen.getByRole('textbox', { name: /What should change/ }) as HTMLInputElement).value).toBe('keep it calm and friendly: a fox on a roof')
    fireEvent.click(screen.getByRole('button', { name: 'Redraw' }))
    expect(onRedraw).toHaveBeenCalledWith({ change: 'keep it calm and friendly: a fox on a roof', surprise: false })
  })
})
