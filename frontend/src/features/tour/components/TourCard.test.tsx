import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { view } from '../machine'
import { TOUR_STEPS } from '../steps'
import { TourCard } from './TourCard'

const handlers = () => ({ onNext: vi.fn(), onBack: vi.fn(), onSkip: vi.fn(), onAction: vi.fn() })
const at = (index: number) => ({ status: 'running' as const, index })
const stepAt = (index: number) => {
  const step = TOUR_STEPS[index]
  if (!step) throw new Error(`no step ${index}`)
  return step
}

describe('TourCard', () => {
  it('is a labelled dialog that takes focus on its title and shows n of N', () => {
    const step = stepAt(3)
    render(<TourCard step={step} view={view(TOUR_STEPS, at(3), { anchor: true, done: false, blocked: false }, 0)} rect={null} layer={null} {...handlers()} />)
    const dialog = screen.getByRole('dialog', { name: 'Muse Spark directs each paragraph into a shot' })
    expect(dialog.getAttribute('aria-modal')).toBe('false')
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Muse Spark directs each paragraph into a shot' }))
    expect(screen.getByTestId('tour-progress').textContent).toBe('4 of 12')
  })

  it('while waiting says what is happening and how long, and holds Next', () => {
    const h = handlers()
    render(<TourCard step={stepAt(6)} view={view(TOUR_STEPS, at(6), { anchor: false, done: false, blocked: false }, 3)} rect={null} layer={null} {...h} />)
    expect(screen.getByText('Muse Image is drawing the first panels.')).toBeTruthy()
    expect(screen.getByText('About 30 seconds.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Next' })).toHaveProperty('disabled', true)
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(h.onBack).toHaveBeenCalled()
  })

  it('Esc closes the tour, and the voice step starts the sample story', () => {
    const h = handlers()
    render(<TourCard step={stepAt(1)} view={view(TOUR_STEPS, at(1), { anchor: true, done: false, blocked: false }, 0)} rect={null} layer={null} {...h} />)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(h.onSkip).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Start the sample story' }))
    expect(h.onAction).toHaveBeenCalled()
  })
})
