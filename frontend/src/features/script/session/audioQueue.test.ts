import { describe, expect, it } from 'vitest'
import { AudioQueue, type Player } from './audioQueue'

function fakePlayer() {
  const played: string[] = []
  const player = {
    src: '',
    paused: 0,
    play: async () => void played.push(player.src),
    pause: () => void (player.paused += 1),
    onended: null as Player['onended'],
    onerror: null as Player['onerror'],
  }
  const end = () => player.onended?.call(player as unknown as HTMLAudioElement, new Event('ended'))
  return { player, played, end }
}

describe('AudioQueue', () => {
  it('plays clips in paragraph order as they arrive, holds on pause and resumes', async () => {
    const { player, played, end } = fakePlayer()
    const now: (number | null)[] = []
    const q = new AudioQueue((p) => now.push(p), player as unknown as Player)

    q.add(0, '/a.wav')
    q.add(0, '/a.wav') // once only
    q.add(2, '/c.wav')
    q.add(1, '/b.wav')
    expect(played).toEqual(['/a.wav'])
    q.pause()
    end()
    expect(played).toEqual(['/a.wav']) // paused: the next clip waits
    q.resume()
    expect(played).toEqual(['/a.wav', '/b.wav'])
    end()
    end()
    expect(played).toEqual(['/a.wav', '/b.wav', '/c.wav'])
    expect(q.idle).toBe(true)
    expect(now).toEqual([0, 1, 2, null])
  })
})
