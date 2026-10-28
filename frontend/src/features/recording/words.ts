/** The transcript as the narrator sees it: whitespace-separated words, punctuation attached. */
export function words(text: string): string[] {
  return text.split(/\s+/).filter(Boolean)
}

/** Replace the word at `index` (trimmed; empty removes it) and rebuild the line with single spaces. */
export function replaceWord(text: string, index: number, replacement: string): string {
  const list = words(text)
  if (index < 0 || index >= list.length) return text
  const fixed = replacement.trim()
  return [...list.slice(0, index), ...(fixed ? [fixed] : []), ...list.slice(index + 1)].join(' ')
}
