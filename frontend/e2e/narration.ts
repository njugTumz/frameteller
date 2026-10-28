import { readFileSync, writeFileSync } from 'node:fs'

// The live run narrates spikes/fixtures/narration.wav through Chromium's fake microphone.
export const BYTES_PER_MS = 48 // 24 kHz mono s16le, what the app sends
export const LEAD_MS = 3000 // silence put before the narration, so the audio clock's start-up only loses silence
// Paragraph beats from docs/spikes/2026-10-28-findings.md (ADR 0008), 200 ms before each paragraph's onset.
export const BEATS_MS = [5500, 15800, 21800, 28400, 33600, 40500]
const ENVELOPE_MS = 20

/** The PCM samples of a 16-bit WAV (its "data" chunk) and its sample rate. */
export function readWav(path: string): { samples: Int16Array; rate: number } {
  const file = readFileSync(path)
  const view = new DataView(file.buffer, file.byteOffset, file.byteLength)
  const tag = (at: number) => String.fromCharCode(...file.subarray(at, at + 4))
  let rate = 0
  for (let at = 12; at + 8 <= file.length; ) {
    const size = view.getUint32(at + 4, true)
    if (tag(at) === 'fmt ') rate = view.getUint32(at + 12, true)
    if (tag(at) === 'data') return { samples: pcm(file.slice(at + 8, at + 8 + size)), rate }
    at += 8 + size + (size % 2)
  }
  throw new Error(`no data chunk in ${path}`)
}

/** s16le bytes as samples. */
export function pcm(bytes: Uint8Array): Int16Array {
  const copy = bytes.slice(0, bytes.length - (bytes.length % 2)) // aligned, owned
  return new Int16Array(copy.buffer)
}

/** Write a mono 16-bit WAV of `samples` with LEAD_MS of silence in front. */
export function writePadded(source: string, target: string): void {
  const { samples, rate } = readWav(source)
  const lead = Math.round((rate * LEAD_MS) / 1000)
  const dataBytes = (lead + samples.length) * 2
  const out = new Uint8Array(44 + dataBytes)
  const view = new DataView(out.buffer)
  const ascii = (at: number, text: string) => [...text].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)))
  ascii(0, 'RIFF')
  view.setUint32(4, 36 + dataBytes, true)
  ascii(8, 'WAVEfmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, rate, true)
  view.setUint32(28, rate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  ascii(36, 'data')
  view.setUint32(40, dataBytes, true)
  out.set(new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength), 44 + lead * 2)
  writeFileSync(target, out)
}

/** Log energy per ENVELOPE_MS window. */
export function envelope(samples: Int16Array, rate: number): number[] {
  const win = (rate * ENVELOPE_MS) / 1000
  const out: number[] = []
  for (let i = 0; i + win <= samples.length; i += win) {
    let sum = 0
    for (let j = i; j < i + win; j++) sum += (samples[j] ?? 0) ** 2
    out.push(Math.log10(1 + sum / win))
  }
  return out
}

/**
 * Where in the file the first byte the app sent came from, in ms: the lag that best lines up the sent audio's
 * energy with the file's (Pearson correlation). Echo cancellation and gain control change levels, not timing.
 */
export function alignSent(sent: number[], file: number[], maxLagMs: number): { lagMs: number; score: number } {
  let best = { lagMs: 0, score: -Infinity }
  for (let lag = 0; lag <= maxLagMs / ENVELOPE_MS; lag++) {
    const n = Math.min(sent.length, file.length - lag)
    if (n < 50) break
    let sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0
    for (let i = 0; i < n; i++) {
      const a = sent[i] ?? 0, b = file[i + lag] ?? 0
      sa += a; sb += b; saa += a * a; sbb += b * b; sab += a * b
    }
    const cov = sab - (sa * sb) / n
    const score = cov / Math.sqrt((saa - (sa * sa) / n) * (sbb - (sb * sb) / n) || 1)
    if (score > best.score) best = { lagMs: lag * ENVELOPE_MS, score }
  }
  return best
}
