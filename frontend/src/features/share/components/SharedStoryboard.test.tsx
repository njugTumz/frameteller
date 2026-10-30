import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { emojiFlags } from '../../../test/flags'
import type { SharedProject } from '../../../shared/api/types'
import { SharedStoryboard } from './SharedStoryboard'

const PROJECT: SharedProject = {
  title: 'Rooftop Kite',
  style: 'pencil',
  shots: [],
  animatic: { url: '/shares/t/animatic', duration_ms: 12000 },
  public: false,
  narrated_by: 'Brandon',
}

describe('SharedStoryboard', () => {
  it('says which voice narrated the animatic', () => {
    render(<SharedStoryboard project={PROJECT} src={(p) => p ?? null} onMakeYourOwn={vi.fn()} />)
    expect(screen.getByText(/Narrated by Brandon \(AI voice\)/)).toBeTruthy()
  })

  it('says nothing about a voice when the author narrated it', () => {
    render(<SharedStoryboard project={{ ...PROJECT, narrated_by: null }} src={(p) => p ?? null} onMakeYourOwn={vi.fn()} />)
    expect(screen.queryByText(/Narrated by/)).toBeNull()
  })

  it('shows the gallery byline only for a storyboard in the gallery', () => {
    const { rerender } = render(<SharedStoryboard project={{ ...PROJECT, creator: { name: 'Ama', country: 'KE' } }} src={(p) => p ?? null} onMakeYourOwn={vi.fn()} />)
    expect(screen.getByTestId('shared-byline').textContent).toBe('by Ama · 🇰🇪 Kenya')
    rerender(<SharedStoryboard project={{ ...PROJECT, creator: { name: '', country: '' } }} src={(p) => p ?? null} onMakeYourOwn={vi.fn()} />)
    expect(screen.getByTestId('shared-byline').textContent).toBe('by an anonymous storyteller')
    rerender(<SharedStoryboard project={{ ...PROJECT, creator: null }} src={(p) => p ?? null} onMakeYourOwn={vi.fn()} />)
    expect(screen.queryByTestId('shared-byline')).toBeNull()
  })

  it('reads "by <name> · <country>" where flags would show as letters', () => {
    emojiFlags(false)
    render(<SharedStoryboard project={{ ...PROJECT, creator: { name: 'Ama', country: 'AE' } }} src={(p) => p ?? null} onMakeYourOwn={vi.fn()} />)
    expect(screen.getByTestId('shared-byline').textContent).toBe('by Ama · United Arab Emirates')
  })
})
