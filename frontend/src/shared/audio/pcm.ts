/**
 * Microphone audio → what the session WebSocket expects: PCM s16le, mono, 24 kHz, in ~80 ms frames
 * (docs/api-events.md). Pure functions, shared by the AudioWorklet and the tests.
 */

export const TARGET_RATE = 24_000
export const FRAME_MS = 80
export const FRAME_SAMPLES = (TARGET_RATE * FRAME_MS) / 1000 // 1920 samples = 3840 bytes
export const BYTES_PER_MS = (TARGET_RATE * 2) / 1000

/**
 * Resample to 24 kHz by averaging each output sample's window of input samples: a box filter, enough to keep
 * speech from aliasing when the device runs at 44.1 or 48 kHz. State carries across calls, so 128-sample
 * worklet blocks join up without clicks or drift.
 */
export class Downsampler {
  private readonly ratio: number
  private position = 0 // where the next output sample starts, in input samples, relative to `carry`
  private carry: Float32Array = new Float32Array(0)

  constructor(inputRate: number) {
    if (!(inputRate >= TARGET_RATE)) throw new RangeError(`input rate ${inputRate} Hz is below ${TARGET_RATE} Hz`)
    this.ratio = inputRate / TARGET_RATE
  }

  process(input: Float32Array): Float32Array {
    const data = new Float32Array(this.carry.length + input.length)
    data.set(this.carry)
    data.set(input, this.carry.length)
    const out: number[] = []
    let pos = this.position
    while (pos + this.ratio <= data.length) {
      const start = Math.floor(pos)
      const end = Math.floor(pos + this.ratio)
      let sum = 0
      for (let i = start; i < end; i++) sum += data[i] ?? 0
      out.push(end > start ? sum / (end - start) : (data[start] ?? 0))
      pos += this.ratio
    }
    const keepFrom = Math.floor(pos)
    this.carry = data.slice(keepFrom)
    this.position = pos - keepFrom
    return Float32Array.from(out)
  }
}

/** Float [-1, 1] → signed 16-bit, clamped. */
export function toInt16(samples: Float32Array): Int16Array {
  const out = new Int16Array(samples.length)
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0))
    out[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff)
  }
  return out
}

/** Little-endian bytes, whatever the platform's byte order. */
export function toLittleEndian(samples: Int16Array): ArrayBuffer {
  const buffer = new ArrayBuffer(samples.length * 2)
  const view = new DataView(buffer)
  for (let i = 0; i < samples.length; i++) view.setInt16(i * 2, samples[i] ?? 0, true)
  return buffer
}

/** Collects samples and hands back whole frames of FRAME_SAMPLES. */
export class FrameChunker {
  private pending = new Int16Array(0)
  private readonly frameSamples: number

  constructor(frameSamples = FRAME_SAMPLES) {
    this.frameSamples = frameSamples
  }

  push(samples: Int16Array): Int16Array[] {
    const data = new Int16Array(this.pending.length + samples.length)
    data.set(this.pending)
    data.set(samples, this.pending.length)
    const frames: Int16Array[] = []
    let at = 0
    for (; at + this.frameSamples <= data.length; at += this.frameSamples) {
      frames.push(data.slice(at, at + this.frameSamples))
    }
    this.pending = data.slice(at)
    return frames
  }

  /** What is left, for the end of a recording. */
  flush(): Int16Array | null {
    const rest = this.pending
    this.pending = new Int16Array(0)
    return rest.length ? rest : null
  }
}

/** Loudness for the meter: RMS mapped so normal speech reads around the middle. */
export function level(samples: Float32Array): number {
  if (!samples.length) return 0
  let sum = 0
  for (const s of samples) sum += s * s
  const rms = Math.sqrt(sum / samples.length)
  return Math.min(1, Math.sqrt(rms) * 1.6)
}

/** Mix channels to mono. */
export function mixToMono(channels: readonly Float32Array[]): Float32Array {
  const first = channels[0]
  if (!first) return new Float32Array(0)
  if (channels.length === 1) return first
  return Float32Array.from(first, (_, i) => channels.reduce((sum, ch) => sum + (ch[i] ?? 0), 0) / channels.length)
}

/** A WAV container around 24 kHz mono s16le PCM, for one-off dictation uploads. */
export function wav(samples: Int16Array, rate = TARGET_RATE): Blob {
  const header = new DataView(new ArrayBuffer(44))
  const text = (at: number, s: string) => [...s].forEach((c, i) => header.setUint8(at + i, c.charCodeAt(0)))
  const bytes = samples.length * 2
  text(0, 'RIFF')
  header.setUint32(4, 36 + bytes, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  header.setUint32(16, 16, true)
  header.setUint16(20, 1, true) // PCM
  header.setUint16(22, 1, true) // mono
  header.setUint32(24, rate, true)
  header.setUint32(28, rate * 2, true)
  header.setUint16(32, 2, true)
  header.setUint16(34, 16, true)
  text(36, 'data')
  header.setUint32(40, bytes, true)
  return new Blob([header.buffer, toLittleEndian(samples)], { type: 'audio/wav' })
}
