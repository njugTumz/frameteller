/** 4200 → "4.2 s". */
export function seconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`
}

/** 3 → "03": shot numbers read like a storyboard sheet. */
export function shotLabel(n: number): string {
  return String(n).padStart(2, '0')
}

/** "medium_close" → "Medium close". */
export function framingLabel(framing: string): string {
  const words = framing.replace(/_/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}
