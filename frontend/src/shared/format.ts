/** 1 → "1st", 2 → "2nd", 13 → "13th". */
export function ordinal(n: number): string {
  const tens = n % 100
  const suffix = tens >= 11 && tens <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${suffix}`
}

/** 25 → "about 30 s", 130 → "about 2 min": rounded up, never promising more than we know. */
export function aboutWait(seconds: number): string {
  if (seconds < 60) return `about ${Math.max(10, Math.ceil(seconds / 10) * 10)} s`
  return `about ${Math.ceil(seconds / 60)} min`
}

/** A place in a waiting room (ADR 0016): "You're next, about 30 s" or "You're 3rd in line, about 2 min". */
export function inLine(position: number, estimateS: number): string {
  return position <= 1 ? `You're next, ${aboutWait(estimateS)}` : `You're ${ordinal(position)} in line, ${aboutWait(estimateS)}`
}

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
