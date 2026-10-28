/**
 * AudioWorklet: the microphone at the device rate in, 80 ms frames of 24 kHz mono s16le out (as transferable
 * ArrayBuffers), plus a level for the meter about 20 times a second. Runs on the audio thread.
 */
import { Downsampler, FrameChunker, level, mixToMono, toInt16, toLittleEndian } from './pcm'

// The AudioWorklet global scope is not in TypeScript's DOM libs; declare the parts used here.
declare const sampleRate: number
declare function registerProcessor(name: string, processor: new () => AudioWorkletProcessorLike): void
interface AudioWorkletProcessorLike {
  readonly port: MessagePort
  process(inputs: Float32Array[][]): boolean
}
declare const AudioWorkletProcessor: new () => AudioWorkletProcessorLike

export type WorkletMessage = { type: 'frame'; pcm: ArrayBuffer } | { type: 'level'; value: number }

const LEVEL_EVERY_BLOCKS = 18 // 128-sample blocks: about 50 ms at 48 kHz

class Pcm24kProcessor extends AudioWorkletProcessor {
  private readonly down = new Downsampler(sampleRate)
  private readonly chunker = new FrameChunker()
  private blocks = 0
  private peak = 0

  override process(inputs: Float32Array[][]): boolean {
    const channels = inputs[0]
    if (!channels?.length) return true
    const mono = mixToMono(channels)
    this.peak = Math.max(this.peak, level(mono))
    if (++this.blocks >= LEVEL_EVERY_BLOCKS) {
      this.port.postMessage({ type: 'level', value: this.peak } satisfies WorkletMessage)
      this.blocks = 0
      this.peak = 0
    }
    for (const frame of this.chunker.push(toInt16(this.down.process(mono)))) {
      const pcm = toLittleEndian(frame)
      this.port.postMessage({ type: 'frame', pcm } satisfies WorkletMessage, [pcm])
    }
    return true
  }
}

registerProcessor('pcm-24k', Pcm24kProcessor)
