import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ExportPanel } from './ExportPanel'

const base = { ready: true, job: null, videoSrc: null, downloadHref: null, pdfHref: '/pdf', voiceKept: true, error: null }

describe('ExportPanel', () => {
  it('burns captions in by default, as spoken', async () => {
    const onExport = vi.fn()
    render(<ExportPanel {...base} animatic={null} onExport={onExport} />)
    expect(screen.getByLabelText<HTMLInputElement>('Captions in the picture').checked).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Export animatic' }))
    expect(onExport).toHaveBeenCalledWith({ subtitles: true, captionLanguage: null })
  })

  it('asks for captions in another language', async () => {
    const onExport = vi.fn()
    render(<ExportPanel {...base} animatic={null} onExport={onExport} />)
    await userEvent.selectOptions(screen.getByLabelText('Captions in'), 'fr-FR')
    await userEvent.click(screen.getByLabelText('Captions in the picture'))
    await userEvent.click(screen.getByRole('button', { name: 'Export animatic' }))
    expect(onExport).toHaveBeenCalledWith({ subtitles: false, captionLanguage: 'fr-FR' })
  })

  it('offers the .srt beside the MP4', () => {
    const animatic = { url: '/a.mp4', duration_ms: 9000, subtitles: true, voiced: true, caption_language: 'fr-FR', captions_url: '/a.srt' }
    render(<ExportPanel {...base} animatic={animatic} videoSrc="/a.mp4" downloadHref="/a.mp4?download=1" captionsHref="/a.srt?download=1" onExport={vi.fn()} />)
    expect(screen.getByRole('link', { name: 'Captions (.srt)' }).getAttribute('href')).toBe('/a.srt?download=1')
    expect(screen.getByText(/captions · Français · your voice/)).toBeTruthy()
  })
})
