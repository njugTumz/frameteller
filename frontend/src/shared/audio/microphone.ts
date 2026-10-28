import workletUrl from './pcm-worklet.ts?worker&url'
import type { WorkletMessage } from './pcm-worklet'

export type MicProblem = 'blocked' | 'missing' | 'busy' | 'unsupported' | 'lost'

export class MicError extends Error {
  readonly problem: MicProblem

  constructor(problem: MicProblem, message: string) {
    super(message)
    this.name = 'MicError'
    this.problem = problem
  }
}

export interface MicHandlers {
  /** 80 ms of 24 kHz mono s16le PCM. */
  onFrame(pcm: ArrayBuffer): void
  onLevel(level: number): void
  /** The device went away and no other microphone could take over. */
  onLost(error: MicError): void
  /** The device changed (unplugged, or a new default) and recording carried on with another one. */
  onSwitched?(label: string): void
}

export interface Microphone {
  readonly label: string
  close(): Promise<void>
}

const CONSTRAINTS: MediaStreamConstraints = {
  audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
}

export function micError(e: unknown): MicError {
  const name = e instanceof DOMException || e instanceof Error ? e.name : ''
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return new MicError('blocked', 'The browser blocked the microphone.')
    case 'NotFoundError':
    case 'OverconstrainedError':
      return new MicError('missing', 'No microphone was found.')
    case 'NotReadableError':
    case 'AbortError':
      return new MicError('busy', 'Another app is using the microphone.')
    default:
      return e instanceof MicError ? e : new MicError('unsupported', 'This browser cannot record audio here.')
  }
}

/** Ask for the microphone and start streaming frames. Must be called from a click (browsers require a gesture). */
/** The constraints for one device, or the system default. */
export function constraintsFor(deviceId?: string): MediaStreamConstraints {
  if (!deviceId) return CONSTRAINTS
  return { audio: { ...(CONSTRAINTS.audio as MediaTrackConstraints), deviceId: { exact: deviceId } } }
}

export async function openMicrophone(
  handlers: MicHandlers,
  media: MediaDevices | undefined = navigator.mediaDevices,
  options: { deviceId?: string } = {},
): Promise<Microphone> {
  if (!media?.getUserMedia || typeof AudioWorkletNode === 'undefined') {
    throw new MicError('unsupported', 'This browser cannot record audio here.')
  }
  const devices = media
  let stream: MediaStream
  try {
    stream = await media.getUserMedia(constraintsFor(options.deviceId))
  } catch (e) {
    throw micError(e)
  }

  const context = new AudioContext({ latencyHint: 'interactive' })
  try {
    await context.audioWorklet.addModule(workletUrl)
  } catch {
    stream.getTracks().forEach((t) => t.stop())
    await context.close()
    throw new MicError('unsupported', 'This browser cannot process audio here.')
  }
  if (context.state === 'suspended') await context.resume()

  const node = new AudioWorkletNode(context, 'pcm-24k', { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1, channelCountMode: 'explicit' })
  node.port.onmessage = ({ data }: MessageEvent<WorkletMessage>) => {
    if (data.type === 'frame') handlers.onFrame(data.pcm)
    else handlers.onLevel(data.value)
  }
  // The worklet only runs while connected to the output; a muted gain keeps the room from hearing itself.
  const mute = context.createGain()
  mute.gain.value = 0
  node.connect(mute).connect(context.destination)

  let closed = false
  let source = context.createMediaStreamSource(stream)
  source.connect(node)
  let label = stream.getAudioTracks()[0]?.label || 'Microphone'

  const watch = (s: MediaStream) => s.getAudioTracks().forEach((t) => t.addEventListener('ended', () => void recover()))

  /** The track ended (unplugged, permission revoked): carry on with the default device if there is one. */
  async function recover(): Promise<void> {
    if (closed) return
    try {
      const next = await devices.getUserMedia(CONSTRAINTS)
      if (closed) {
        next.getTracks().forEach((t) => t.stop())
        return
      }
      source.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      stream = next
      source = context.createMediaStreamSource(stream)
      source.connect(node)
      label = stream.getAudioTracks()[0]?.label || 'Microphone'
      watch(stream)
      handlers.onSwitched?.(label)
    } catch (e) {
      const error = micError(e)
      handlers.onLost(error.problem === 'blocked' ? error : new MicError('lost', 'The microphone was disconnected.'))
    }
  }

  /** A new default device (headset plugged in) while the current track still runs: move to it. */
  const onDeviceChange = async () => {
    const current = stream.getAudioTracks()[0]
    if (!current || current.readyState === 'ended') return void recover()
    const inputs = await devices.enumerateDevices().catch(() => [])
    const settings = current.getSettings()
    const stillThere = inputs.some((d) => d.kind === 'audioinput' && d.deviceId === settings.deviceId)
    if (!stillThere) void recover()
  }
  watch(stream)
  devices.addEventListener?.('devicechange', onDeviceChange)

  return {
    get label() {
      return label
    },
    async close() {
      if (closed) return
      closed = true
      devices.removeEventListener?.('devicechange', onDeviceChange)
      node.port.onmessage = null
      source.disconnect()
      node.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      await context.close().catch(() => undefined)
    },
  }
}
