import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MyGalleryEntry } from '../../../shared/api/types'
import { CONSENT, GallerySubmit } from './GallerySubmit'

const base = { ready: true, voiceKept: true, busy: false, error: null, galleryHref: '/gallery', onWithdraw: vi.fn() }
const entry = (status: MyGalleryEntry['status'], note = ''): MyGalleryEntry => ({
  id: 'g1',
  status,
  note,
  audio: 'mine',
  hearts: 2,
  featured: false,
  submitted_at: '2026-11-02T17:00:00Z',
})

describe('GallerySubmit', () => {
  it('needs consent before it submits, with the audio chosen', async () => {
    const onSubmit = vi.fn()
    render(<GallerySubmit {...base} entry={null} onSubmit={onSubmit} />)
    const submit = screen.getByRole('button', { name: 'Submit to gallery' })
    expect(submit).toHaveProperty('disabled', true)
    await userEvent.click(screen.getByLabelText('With the Brandon voice instead'))
    await userEvent.click(screen.getByLabelText(CONSENT))
    await userEvent.click(submit)
    expect(onSubmit).toHaveBeenCalledWith('voice')
  })

  it('offers my voice only when the recording was kept', () => {
    render(<GallerySubmit {...base} voiceKept={false} entry={null} onSubmit={vi.fn()} />)
    expect(screen.getByLabelText<HTMLInputElement>(/With my voice/).disabled).toBe(true)
    expect(screen.getByLabelText<HTMLInputElement>('With the Brandon voice instead').checked).toBe(true)
  })

  it('shows where the entry stands and can withdraw it', async () => {
    const onWithdraw = vi.fn()
    const { rerender } = render(<GallerySubmit {...base} entry={entry('checking')} onSubmit={vi.fn()} onWithdraw={onWithdraw} />)
    expect(screen.getByRole('status').textContent).toMatch(/Checking your storyboard/)
    rerender(<GallerySubmit {...base} entry={entry('published')} onSubmit={vi.fn()} onWithdraw={onWithdraw} />)
    expect(screen.getByRole('link', { name: 'See it in the gallery (2 hearts)' }).getAttribute('href')).toBe('/gallery')
    await userEvent.click(screen.getByRole('button', { name: 'Withdraw from the gallery' }))
    expect(onWithdraw).toHaveBeenCalled()
    rerender(<GallerySubmit {...base} entry={entry('failed', 'The animatic could not be rendered.')} onSubmit={vi.fn()} onWithdraw={onWithdraw} />)
    expect(screen.getByRole('alert').textContent).toMatch(/could not be rendered/)
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  })
})
