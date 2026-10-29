import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { StartScreen } from './StartScreen'

const props = (over: Partial<Parameters<typeof StartScreen>[0]> = {}) => ({
  form: { title: '', style: 'pencil' as const, names: '', keepAudio: true },
  creating: false,
  error: null,
  wakeNotice: null,
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  ...over,
})

describe('StartScreen', () => {
  it('links to the privacy page', () => {
    render(<StartScreen {...props()} />)
    expect(screen.getByRole('link', { name: 'What we keep, and for how long' }).getAttribute('href')).toBe('/privacy')
  })

  it('says the studio is full for today and starts no story', () => {
    render(<StartScreen {...props({ full: true })} />)
    expect(screen.getByText('The studio is full for today. Come back tomorrow.')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Open the studio' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
