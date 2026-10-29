import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
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
})
