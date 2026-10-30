import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Voices } from '../../../shared/api/types'
import { StartScreen, type StartForm } from './StartScreen'

const FORM: StartForm = {
  title: '',
  style: 'pencil',
  names: '',
  keepAudio: true,
  mode: 'narrate',
  script: '',
  format: 'text',
  voice: 'en-US-AvaMultilingualNeural',
  language: 'en-US',
}

const VOICES: Voices = {
  available: true,
  default: 'en-US-AvaMultilingualNeural',
  voices: [
    {
      name: 'en-US-AvaMultilingualNeural',
      display_name: 'Ava',
      gender: 'Female',
      accent: 'en-US',
      languages: [
        { code: 'en', locale: 'en-US', name: 'English' },
        { code: 'fr', locale: 'fr-FR', name: 'Français' },
      ],
      preview_url: '/voices/en-US-AvaMultilingualNeural/preview',
    },
    {
      name: 'en-GB-AdaMultilingualNeural',
      display_name: 'Ada',
      gender: 'Female',
      accent: 'en-GB',
      languages: [{ code: 'en', locale: 'en-GB', name: 'English' }],
      preview_url: '/voices/en-GB-AdaMultilingualNeural/preview',
    },
  ],
}

const props = (over: Partial<Parameters<typeof StartScreen>[0]> = {}) => ({
  form: FORM,
  creating: false,
  error: null,
  wakeNotice: null,
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  ...over,
})

describe('StartScreen', () => {
  it('offers a sample story when a voice can read it', () => {
    const onSample = vi.fn()
    const { rerender } = render(<StartScreen {...props()} />)
    expect(screen.queryByRole('button', { name: 'Try a sample story' })).toBeNull()
    rerender(<StartScreen {...props({ onSample })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Try a sample story' }))
    expect(onSample).toHaveBeenCalledOnce()
  })

  it('links to the privacy page', () => {
    render(<StartScreen {...props()} />)
    expect(screen.getByRole('link', { name: 'What we keep, and for how long' }).getAttribute('href')).toBe('/privacy')
  })

  it('says the studio is full for today and starts no story', () => {
    render(<StartScreen {...props({ full: true })} />)
    expect(screen.getByText('The studio is full for today. Come back tomorrow.')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Open the studio' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('offers three ways to tell it, and Read it to me only when voices are available', () => {
    const onChange = vi.fn()
    const { rerender } = render(<StartScreen {...props({ onChange })} />)
    expect(screen.getAllByRole('radio', { name: /Narrate|Teleprompter|Read it to me/ })).toHaveLength(3)
    expect((screen.getByRole('radio', { name: /Read it to me/ }) as HTMLInputElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('radio', { name: /Teleprompter/ }))
    expect(onChange).toHaveBeenCalledWith({ mode: 'teleprompter' })

    rerender(<StartScreen {...props({ onChange, voices: VOICES })} />)
    expect((screen.getByRole('radio', { name: /Read it to me/ }) as HTMLInputElement).disabled).toBe(false)
  })

  it('takes a script for the teleprompter, with its length against the limit', () => {
    const onChange = vi.fn()
    render(<StartScreen {...props({ onChange, form: { ...FORM, mode: 'teleprompter', script: 'Lena waves.' } })} />)
    expect(screen.getByText('11 / 4,000')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Your script'), { target: { value: 'INT. ROOF - NIGHT\n\nLena waves.' } })
    expect(onChange).toHaveBeenCalledWith({ script: 'INT. ROOF - NIGHT\n\nLena waves.', format: 'fountain' })
    expect(screen.getByLabelText('Keep my narration for the animatic')).toBeTruthy()
  })

  it('picks a voice and a language for Read it to me, keeping the language when the voice speaks it', () => {
    const onChange = vi.fn()
    render(<StartScreen {...props({ onChange, voices: VOICES, form: { ...FORM, mode: 'read', script: 'Lena waves.', language: 'fr-FR' } })} />)
    expect(screen.queryByLabelText('Keep my narration for the animatic')).toBeNull() // nobody records
    expect([...screen.getByLabelText<HTMLSelectElement>('Language').options].map((o) => o.text)).toEqual(['English', 'Français'])
    fireEvent.click(screen.getByRole('radio', { name: /Ada/ }))
    expect(onChange).toHaveBeenCalledWith({ voice: 'en-GB-AdaMultilingualNeural', language: 'en-GB' }) // Ada reads English only
    expect(screen.getByRole('button', { name: 'Hear Ava' })).toBeTruthy()
  })
})
