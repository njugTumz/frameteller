import { describe, expect, it } from 'vitest'
import { initialScript, paragraphs, reduceScript } from './store'

const EPISODES = [
  { number: 1, paragraphs: [{ narration: 'Lena waves.', direction: 'Wide shot. Lena waves.' }] },
  { number: 2, paragraphs: [{ narration: 'The kite returns.', direction: 'The kite returns.' }] },
]

describe('reduceScript', () => {
  it('keeps the paragraphs the server split and follows the teleprompter', () => {
    let s = reduceScript(initialScript, { type: 'script.accepted', episodes: EPISODES })
    s = reduceScript(s, { type: 'teleprompter.advanced', paragraph: 1 })
    expect(s.current).toBe(1)
    expect(paragraphs(s.episodes)).toEqual([
      { index: 0, episode: 1, narration: 'Lena waves.', direction: 'Wide shot. Lena waves.' },
      { index: 1, episode: 2, narration: 'The kite returns.', direction: 'The kite returns.' },
    ])
  })

  it('reads, pauses for the listener or an episode break, and resumes', () => {
    let s = reduceScript(initialScript, { type: 'session.started', mode: 'read' })
    expect(s.reading).toBe('reading')
    s = reduceScript(s, { type: 'script.voiced', paragraph: 0, episode: 1, text: 'Lena salue.', original: 'Lena waves.', audio_url: '/media/a.wav', duration_ms: 900 })
    s = reduceScript(s, { type: 'script.voiced', paragraph: 0, episode: 1, text: 'Lena salue.', original: 'Lena waves.', audio_url: '/media/a.wav', duration_ms: 900 })
    expect(s.clips).toHaveLength(1) // a repeated event replaces, never duplicates
    s = reduceScript(s, { type: 'script.paused', next_paragraph: 1, next_episode: 2, reason: 'episode' })
    expect([s.reading, s.nextEpisode]).toEqual(['episode-break', 2])
    s = reduceScript(s, { type: 'script.resumed', next_paragraph: 1 })
    expect([s.reading, s.nextEpisode]).toEqual(['reading', null])
    s = reduceScript(s, { type: 'script.paused', next_paragraph: 1, next_episode: 2, reason: 'user' })
    expect(s.reading).toBe('paused')
    s = reduceScript(s, { type: 'session.ended', turns: 2, shots: 2 })
    expect(s.reading).toBe('done')
  })

  it('leaves narration sessions alone', () => {
    expect(reduceScript(initialScript, { type: 'session.started', mode: 'narrate' })).toBe(initialScript)
    expect(reduceScript(initialScript, { type: 'session.ended', turns: 1, shots: 1 })).toBe(initialScript)
  })
})
