import { beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeSocket } from '../../../test/fakeSocket'
import { MicError, type MicHandlers, type Microphone } from '../../../shared/audio/microphone'
import { useRecordingStore } from '../store'
import { MAX_BACKLOG_FRAMES, Narration, RECONNECTED } from './narration'

function fakeMic() {
  const mic = { handlers: null as MicHandlers | null, closed: false }
  const openMic = vi.fn(async (handlers: MicHandlers, _media?: MediaDevices, _options?: { deviceId?: string }): Promise<Microphone> => {
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
    expect(socket.json[0]).toEqual({ mode: 'narrate', keywords: ['Mira', 'Grey Cat'], keep_audio: true })
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

  it('keeps audio captured while connecting and sends it first, up to 2 s', async () => {
    const { mic, openMic } = fakeMic()
    const n = new Narration('p1', { store: useRecordingStore, openMic, socketFactory: FakeSocket.factory })
    const starting = n.start()
    await flush()
    for (let i = 0; i < MAX_BACKLOG_FRAMES + 5; i++) mic.handlers?.onFrame(new Uint8Array([i % 256, 0]).buffer)
    const socket = FakeSocket.latest()
    expect(socket.binary).toHaveLength(0)
    socket.start()
    await starting
    expect(socket.binary).toHaveLength(MAX_BACKLOG_FRAMES)
    expect(new Uint8Array(socket.binary[0] ?? new ArrayBuffer(1))[0]).toBe(5) // the oldest frames were dropped, the latest kept
    mic.handlers?.onFrame(new ArrayBuffer(2))
    expect(socket.binary).toHaveLength(MAX_BACKLOG_FRAMES + 1)
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

  it('keeps the recording only when the narrator agreed', async () => {
    const { openMic } = fakeMic()
    useRecordingStore.getState().set({ keepAudio: false })
    const n = new Narration('p1', { store: useRecordingStore, openMic, socketFactory: FakeSocket.factory })
    await started(n)
    expect(FakeSocket.latest().json[0]).toMatchObject({ keep_audio: false })
    expect(useRecordingStore.getState().micLabel).toBe('Fake mic')
  })

  it('switches to another microphone mid-session without a new session', async () => {
    const { mic, openMic } = fakeMic()
    const n = new Narration('p1', { store: useRecordingStore, openMic, socketFactory: FakeSocket.factory })
    await started(n)
    useRecordingStore.getState().apply({ type: 'audio.silent', after_ms: 8000, level: 0.001 })

    await n.useMicrophone('usb-mic')

    expect(openMic).toHaveBeenCalledTimes(2)
    expect(openMic.mock.calls[1]?.[2]).toEqual({ deviceId: 'usb-mic' })
    expect(mic.closed).toBe(true)
    expect(FakeSocket.all).toHaveLength(1)
    expect(useRecordingStore.getState()).toMatchObject({ deviceId: 'usb-mic', silent: false })
  })
})
