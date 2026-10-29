import { beforeEach, describe, expect, it } from 'vitest'
import { FakeSocket } from '../../../test/fakeSocket'
import { useRecordingStore } from '../../recording/store'
import { useScriptStore } from '../store'
import type { Player } from './audioQueue'
import { Reader } from './reader'

const flush = () => new Promise((r) => setTimeout(r, 0))

function player() {
  const played: string[] = []
  const p = { src: '', play: async () => void played.push(p.src), pause: () => undefined, onended: null, onerror: null }
  return { p: p as unknown as Player, played }
}

describe('Reader', () => {
  beforeEach(() => {
    FakeSocket.all = []
    useRecordingStore.getState().reset()
    useScriptStore.getState().reset()
  })

  it('starts a read session with the script, voice and language, plays each voiced paragraph, pauses and continues', async () => {
    const { p, played } = player()
    const seen: string[] = []
    const reader = new Reader('p1', { recording: useRecordingStore, script: useScriptStore, socketFactory: FakeSocket.factory, player: p })
    reader.use((e) => {
      seen.push(e.type)
      useScriptStore.getState().apply(e) // the studio's dispatch
    })

    const starting = reader.start({ script: 'Lena waves.', format: 'text', voice: 'en-US-BrandonMultilingualNeural', language: 'fr-FR' })
    await flush()
    const socket = FakeSocket.latest()
    socket.open()
    socket.emit({ type: 'session.started', mode: 'read' })
    await starting
    expect(socket.json[0]).toEqual({
      mode: 'read',
      keywords: [],
      keep_audio: false,
      script: 'Lena waves.',
      script_format: 'text',
      voice: 'en-US-BrandonMultilingualNeural',
      language: 'fr-FR',
    })
    expect(useRecordingStore.getState().telling).toBe('live')

    socket.emit({ type: 'script.voiced', paragraph: 0, episode: 1, text: 'Lena salue.', original: 'Lena waves.', audio_url: '/media/projects/p1/speech/a.wav', duration_ms: 900 })
    expect(played).toEqual(['http://localhost:8000/media/projects/p1/speech/a.wav'])
    expect(useScriptStore.getState().clips).toHaveLength(1)

    reader.pause()
    expect(useScriptStore.getState().reading).toBe('paused')
    reader.resume()
    reader.stop()
    expect(socket.json.slice(1)).toEqual([{ type: 'pause' }, { type: 'continue' }, { type: 'end' }])
    expect(useRecordingStore.getState().telling).toBe('finishing')
    expect(seen).toContain('script.voiced')
  })

  it('says why when the server refuses the script', async () => {
    const reader = new Reader('p1', { recording: useRecordingStore, script: useScriptStore, socketFactory: FakeSocket.factory })
    const starting = reader.start({ script: 'x', format: 'text', voice: 'v', language: 'en-US' })
    await flush()
    FakeSocket.latest().open()
    FakeSocket.latest().serverClose(4400)
    await starting
    expect(useRecordingStore.getState().problem?.kind).toBe('connection')
    expect(useRecordingStore.getState().telling).toBe('idle')
  })
})
