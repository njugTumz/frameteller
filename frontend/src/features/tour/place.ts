export const GAP = 12
export const EDGE = 16

interface Box {
  top: number
  bottom: number
  left: number
}
interface Size {
  width: number
  height: number
}

/**
 * Where the card goes beside the element it explains: below it if it fits, else above, and always inside the
 * viewport, so Next stays reachable even when the element has grown or moved out of view.
 */
export function placeCard(rect: Box, size: Size, viewport: Size): { top: number; left: number } {
  const below = rect.bottom + GAP
  const above = rect.top - GAP - size.height
  const lowest = viewport.height - size.height - EDGE
  const preferred = below <= lowest ? below : above >= EDGE ? above : lowest
  const top = Math.max(EDGE, Math.min(preferred, lowest))
  const left = Math.max(EDGE, Math.min(rect.left, viewport.width - size.width - EDGE))
  return { top, left }
}
