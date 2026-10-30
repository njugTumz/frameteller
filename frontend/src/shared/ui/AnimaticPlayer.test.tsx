import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AnimaticPlayer } from './AnimaticPlayer'

describe('AnimaticPlayer', () => {
  it('never autoplays muted, and Play with sound turns the sound on and plays', () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
    render(<AnimaticPlayer src="/a.mp4" label="The animatic" testId="animatic-player" />)
    const video = screen.getByTestId<HTMLVideoElement>('animatic-player')
    expect(video.autoplay).toBe(false)
    expect(video.muted).toBe(false)
    video.muted = true
    video.volume = 0.2
    fireEvent.click(screen.getByRole('button', { name: /play with sound/i }))
    expect(play).toHaveBeenCalled()
    expect(video.muted).toBe(false)
    expect(video.volume).toBe(1)
    expect(screen.queryByRole('button', { name: /play with sound/i })).toBeNull()
    play.mockRestore()
  })

  it('says when the animatic has no voice', () => {
    render(<AnimaticPlayer src="/a.mp4" label="The animatic" testId="animatic-player" voiced={false} />)
    expect(screen.getByRole('button', { name: /silent/i })).toBeTruthy()
  })
})
