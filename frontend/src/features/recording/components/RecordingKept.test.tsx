import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RecordingKept } from './RecordingKept'

describe('RecordingKept', () => {
  it('lets the narrator listen to the recording next to Delete my recording', () => {
    const onDelete = vi.fn()
    render(<RecordingKept durationMs={61_000} recordings={['/media/rec.wav']} onDelete={onDelete} />)
    expect(screen.getByText('Listen to your narration')).toBeTruthy()
    const audio = screen.getByLabelText<HTMLAudioElement>('Your narration')
    expect(audio.getAttribute('src')).toBe('/media/rec.wav')
    expect(audio.controls).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Delete my recording' }))
    expect(onDelete).toHaveBeenCalled()
  })

  it('numbers the parts of a story recorded in several sessions', () => {
    render(<RecordingKept durationMs={9_000} recordings={['/a.wav', '/b.wav']} onDelete={() => undefined} />)
    expect(screen.getByLabelText('Your narration, part 2')).toBeTruthy()
  })
})
