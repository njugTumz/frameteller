import { describe, expect, it } from 'vitest'
import { Downsampler, FRAME_SAMPLES, FrameChunker, level, mixToMono, toInt16, toLittleEndian, wav } from './pcm'

const tone = (rate: number, seconds: number, hz = 440) =>
  Float32Array.from({ length: Math.round(rate * seconds) }, (_, i) => 0.5 * Math.sin((2 * Math.PI * hz * i) / rate))

describe('Downsampler', () => {
  it.each([48_000, 44_100, 24_000])('turns one second at %i Hz into 24,000 samples, block by block', (rate) => {
    const down = new Downsampler(rate)
    const input = tone(rate, 1)
    let total = 0
    for (let at = 0; at < input.length; at += 128) total += down.process(input.subarray(at, at + 128)).length
    expect(Math.abs(total - 24_000)).toBeLessThanOrEqual(1)
  })

  it('keeps the waveform: averaging pairs at 48 kHz', () => {
    const out = new Downsampler(48_000).process(Float32Array.from([0.2, 0.4, -0.6, -0.2]))
    expect(Array.from(out)).toEqual([expect.closeTo(0.3), expect.closeTo(-0.4)])
  })

  it('refuses rates below 24 kHz', () => {
    expect(() => new Downsampler(16_000)).toThrow(RangeError)
  })
})

describe('PCM encoding', () => {
  it('clamps and scales to signed 16-bit', () => {
    expect(Array.from(toInt16(Float32Array.from([0, 1, -1, 2, -2, 0.5])))).toEqual([0, 32767, -32768, 32767, -32768, 16384])
  })

  it('writes little-endian bytes', () => {
    const bytes = new Uint8Array(toLittleEndian(Int16Array.from([1, -2])))
    expect(Array.from(bytes)).toEqual([0x01, 0x00, 0xfe, 0xff])
  })

  it('chunks into 80 ms frames (3,840 bytes) and keeps the remainder', () => {
    const chunker = new FrameChunker()
    expect(chunker.push(new Int16Array(FRAME_SAMPLES - 1))).toHaveLength(0)
    const frames = chunker.push(new Int16Array(FRAME_SAMPLES + 5))
    expect(frames).toHaveLength(2)
    expect(frames.every((f) => f.length * 2 === 3840)).toBe(true)
    expect(chunker.flush()?.length).toBe(4)
    expect(chunker.flush()).toBeNull()
  })

  it('wraps PCM in a 24 kHz mono WAV header', async () => {
    const blob = wav(new Int16Array(24))
    const view = new DataView(await blob.arrayBuffer())
    expect(blob.size).toBe(44 + 48)
    expect(view.getUint32(24, true)).toBe(24_000)
    expect(view.getUint16(22, true)).toBe(1)
  })
})

describe('level and mixing', () => {
  it('is zero for silence and higher for louder speech', () => {
    expect(level(new Float32Array(128))).toBe(0)
    expect(level(tone(48_000, 0.01))).toBeGreaterThan(level(Float32Array.from(tone(48_000, 0.01), (s) => s / 10)))
  })

  it('mixes stereo to mono', () => {
    expect(Array.from(mixToMono([Float32Array.from([1, 0]), Float32Array.from([0, 1])]))).toEqual([0.5, 0.5])
  })
})
