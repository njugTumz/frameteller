import { vi } from 'vitest'
import { resetFlagSupport } from '../shared/creator'

/**
 * Makes the canvas draw flag emoji the way a browser would: in colour (macOS, iOS, Android), or as plain letters
 * (Windows, or no emoji font). jsdom has no canvas of its own.
 */
export function emojiFlags(drawn: boolean) {
  const pixel = drawn ? [200, 30, 40, 255] : [20, 20, 20, 255]
  const data = new Uint8ClampedArray(24 * 24 * 4)
  for (let i = 0; i < data.length; i += 4) data.set(i < 400 ? pixel : [0, 0, 0, 0], i)
  const ctx = { font: '', fillStyle: '', textBaseline: '', fillText: vi.fn(), getImageData: () => ({ data }) }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D)
  resetFlagSupport()
}
