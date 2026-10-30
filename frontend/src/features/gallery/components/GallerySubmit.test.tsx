import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { emojiFlags } from '../../../test/flags'
import type { MyGalleryEntry } from '../../../shared/api/types'
import { CONSENT, GallerySubmit } from './GallerySubmit'

const base = { ready: true, voiceKept: true, busy: false, error: null, galleryHref: '/gallery', codes: ['AE', 'JP', 'KE'], suggested: 'KE', onSign: vi.fn(), onWithdraw: vi.fn() }
const entry = (status: MyGalleryEntry['status'], note = ''): MyGalleryEntry => ({
  id: 'g1',
  status,
  note,
  audio: 'mine',
  hearts: 2,
  featured: false,
  submitted_at: '2026-11-02T17:00:00Z',
  creator: { name: '', country: '' },
})

describe('GallerySubmit', () => {
  it('needs consent before it submits, with the audio chosen', async () => {
    const onSubmit = vi.fn()
    render(<GallerySubmit {...base} entry={null} onSubmit={onSubmit} />)
    const submit = screen.getByRole('button', { name: 'Submit to gallery' })
    expect(submit).toHaveProperty('disabled', true)
    await userEvent.click(screen.getByLabelText('Publish with the Ava voice instead'))
    await userEvent.click(screen.getByLabelText(CONSENT))
    await userEvent.click(submit)
    expect(onSubmit).toHaveBeenCalledWith('voice', { name: '', country: '' }) // the suggestion is never sent unless chosen
  })

  it('offers my voice only when the recording was kept', () => {
    render(<GallerySubmit {...base} voiceKept={false} entry={null} onSubmit={vi.fn()} />)
    expect(screen.getByLabelText<HTMLInputElement>(/Publish with my voice/).disabled).toBe(true)
    expect(screen.getByLabelText<HTMLInputElement>('Publish with the Ava voice instead').checked).toBe(true)
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

  it('signs with a name and a country; the suggested country only when chosen', async () => {
    const onSubmit = vi.fn()
    render(<GallerySubmit {...base} entry={null} onSubmit={onSubmit} />)
    const name = screen.getByLabelText('Your name')
    expect(name.getAttribute('maxlength')).toBe('40')
    await userEvent.type(name, '  Captain Biscuit ')
    expect(screen.getByLabelText<HTMLSelectElement>('Country').value).toBe('')
    expect(screen.getByTestId('country-suggestion').textContent).toMatch(/A guess from your browser: 🇰🇪 Kenya/)
    await userEvent.click(screen.getByRole('button', { name: 'Use 🇰🇪 Kenya' }))
    expect(screen.getByLabelText<HTMLSelectElement>('Country').value).toBe('KE')
    expect(screen.queryByTestId('country-suggestion')).toBeNull()
    await userEvent.click(screen.getByLabelText(CONSENT))
    await userEvent.click(screen.getByRole('button', { name: 'Submit to gallery' }))
    expect(onSubmit).toHaveBeenCalledWith('mine', { name: 'Captain Biscuit', country: 'KE' })
  })

  it('lists countries by name with flags and codes, after "No country"', () => {
    render(<GallerySubmit {...base} entry={null} onSubmit={vi.fn()} />)
    const options = [...screen.getByLabelText<HTMLSelectElement>('Country').options].map((o) => o.textContent)
    expect(options).toEqual(['No country', '🇯🇵 Japan (JP)', '🇰🇪 Kenya (KE)', '🇦🇪 United Arab Emirates (AE)'])
  })

  it('shows how the entry is signed, and edits or removes the name and country', async () => {
    const onSign = vi.fn().mockResolvedValue(true)
    const signed = { ...entry('published'), creator: { name: 'Ama', country: 'KE' } }
    const { rerender } = render(<GallerySubmit {...base} entry={signed} onSubmit={vi.fn()} onSign={onSign} />)
    expect(screen.getByTestId('my-byline').textContent).toMatch('Shown by Ama · 🇰🇪 Kenya')
    await userEvent.click(screen.getByRole('button', { name: 'Edit name and country' }))
    const name = screen.getByLabelText<HTMLInputElement>('Your name')
    expect(name.value).toBe('Ama')
    await userEvent.clear(name)
    await userEvent.type(name, 'Ama K.')
    await userEvent.selectOptions(screen.getByLabelText('Country'), 'AE')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSign).toHaveBeenLastCalledWith({ name: 'Ama K.', country: 'AE' })
    rerender(<GallerySubmit {...base} entry={{ ...signed, status: 'checking' }} onSubmit={vi.fn()} onSign={onSign} />)
    expect(screen.getByRole('status').textContent).toBe('Checking your new name before it shows in the gallery…')
    expect(screen.queryByRole('button', { name: 'Edit name and country' })).toBeNull() // not while it is checked

    rerender(<GallerySubmit {...base} entry={signed} onSubmit={vi.fn()} onSign={onSign} />)
    await userEvent.click(screen.getByRole('button', { name: 'Edit name and country' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove name and country' }))
    expect(onSign).toHaveBeenLastCalledWith({ name: '', country: '' })
    rerender(<GallerySubmit {...base} entry={entry('published')} onSubmit={vi.fn()} onSign={onSign} />)
    expect(screen.getByTestId('my-byline').textContent).toMatch('Shown by an anonymous storyteller')
    expect(screen.getByRole('button', { name: 'Withdraw from the gallery' })).toBeTruthy() // still possible
  })

  it('offers and lists countries by name where flags would show as letters', async () => {
    emojiFlags(false)
    const onSubmit = vi.fn()
    render(<GallerySubmit {...base} entry={null} onSubmit={onSubmit} />)
    expect(screen.getByTestId('country-suggestion').textContent).toMatch(/A guess from your browser: Kenya\./)
    const options = [...screen.getByLabelText<HTMLSelectElement>('Country').options].map((o) => o.textContent)
    expect(options).toEqual(['No country', 'Japan (JP)', 'Kenya (KE)', 'United Arab Emirates (AE)'])
    await userEvent.click(screen.getByRole('button', { name: 'Use Kenya' }))
    expect(screen.getByLabelText<HTMLSelectElement>('Country').value).toBe('KE')
  })
})
