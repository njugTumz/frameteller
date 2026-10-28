import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeSocket } from '../../../test/fakeSocket'
import { MicError, type MicHandlers, type Microphone } from '../../../shared/audio/microphone'
import { useRecordingStore } from '../store'
import { Narration, RECONNECTED } from './narration'

function fakeMic() {
  const mic = { handlers: null as MicHandlers | null, closed: false }
  const openMic = vi.fn(async (handlers: MicHandlers): Promise<Microphone> => {
    mic.handlers = handlers
    return { label: 'Fake mic', close: async () => void (mic.closed = true) }
  })
  return { mic, openMic }
}

const flush = () => new Promise((r) => setTimeout(r, 0))

async function started(n: Narration) {
  const starting = n.start()
  await flush()
  FakeSocket.latest().start()
  await starting
}

describe('Narration', () => {
  beforeEach(() => {
    FakeSocket.all = []
    useRecordingStore.getState().reset()
  })

  it('sends the start message with keywords, then streams frames and beats', async () => {
    const { mic, openMic } = fakeMic()
    const events: string[] = []
    useRecordingStore.getState().setKeywords(['Mira'])
    const n = new Narration('p1', { store: useRecordingStore, openMic, socketFactory: FakeSocket.factory })
    n.use({ onEvent: (e) => events.push(e.type), extraKeywords: ['Grey Cat', 'Mira'] })

    await started(n)
    const socket = FakeSocket.latest()
    expect(socket.url).toBe('ws://localhost:8000/ws/projects/p1/session')
    expect(socket.json[0]).toEqual({ mode: 'narrate', keywords: ['Mira', 'Grey Cat'] })
    expect(useRecordingStore.getState().telling).toBe('live')

    mic.handlers?.onFrame(new ArrayBuffer(3840))
    expect(socket.binary).toHaveLength(1)
    expect(n.beat()).toBe(true)
    expect(socket.json.at(-1)).toEqual({ type: 'beat' })
    expect(useRecordingStore.getState().beats).toBe(1)

    socket.emit({ type: 'transcript.partial', text: 'Night' })
    expect(useRecordingStore.getState().partial).toBe('Night')
    expect(events).toEqual(['session.started', 'transcript.partial'])
  })

  it('ends the stream on stop, keeps the socket for job updates, and finishes on session.ended', async () => {
    const { mic, openMic } = fakeMic()
    const n = new Narration('p1', { store: useRecordingStore, openMic, socketFactory: FakeSocket.factory })
    await started(n)
    n.stop()
    const socket = FakeSocket.latest()
    expect(socket.json.at(-1)).toEqual({ type: 'end' })
    expect(mic.closed).toBe(true)
    expect(useRecordingStore.getState().telling).toBe('finishing')
    socket.emit({ type: 'session.ended', turns: 2, shots: 2 })
    expect(useRecordingStore.getState().telling).toBe('ended')
    expect(useRecordingStore.getState().connected).toBe(true)
    expect(n.beat()).toBe(false) // nothing to cut once the narration is over
  })

  it('reconnects with a new session after a drop and says so', async () => {
    const { openMic } = fakeMic()
    const n = new Narration('p1', { store: useRecordingStore, openMic, socketFactory: FakeSocket.factory, wait: async () => undefined })
    await started(n)
    FakeSocket.latest().serverClose(1006)
    await flush()
    expect(FakeSocket.all).toHaveLength(2)
    FakeSocket.latest().start()
    await flush()
    expect(useRecordingStore.getState().telling).toBe('live')
    expect(useRecordingStore.getState().notices).toContain(RECONNECTED)
  })

  it('does not reconnect when another tab holds the session', async () => {
    const { openMic } = fakeMic()
    const n = new Narration('p1', { store: useRecordingStore, openMic, socketFactory: FakeSocket.factory, wait: async () => undefined })
    await started(n)
    FakeSocket.latest().serverClose(4409)
    await flush()
    expect(FakeSocket.all).toHaveLength(1)
    expect(useRecordingStore.getState().problem?.message).toMatch(/another tab/)
    expect(useRecordingStore.getState().telling).toBe('idle')
  })

  it('explains a blocked microphone and opens no socket', async () => {
    const openMic = vi.fn(async () => {
      throw new MicError('blocked', 'The browser blocked the microphone.')
    })
    const n = new Narration('p1', { store: useRecordingStore, openMic, socketFactory: FakeSocket.factory })
    await n.start()
    expect(useRecordingStore.getState().problem?.kind).toBe('mic-blocked')
    expect(FakeSocket.all).toHaveLength(0)
  })

  it('opens a socket just for a correction when none is open', async () => {
    const n = new Narration('p1', { store: useRecordingStore, socketFactory: FakeSocket.factory })
    n.correct('t-b1', 'Scene one.')
    FakeSocket.latest().start()
    await flush()
    expect(FakeSocket.latest().json.slice(1)).toEqual([{ type: 'transcript.corrected', turn_id: 't-b1', text: 'Scene one.' }, { type: 'end' }])
    expect(useRecordingStore.getState().correcting).toEqual({ 't-b1': 'sending' })
  })
})
