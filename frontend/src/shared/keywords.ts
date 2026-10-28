/** Names the narrator typed for a story (they bias recognition). Kept per project in this browser only. */
const key = (projectId: string) => `frameteller.keywords.${projectId}`

export function parseNames(text: string): string[] {
  return [...new Set(text.split(/[,\n]/).map((n) => n.trim().slice(0, 40)).filter(Boolean))].slice(0, 50)
}

export function saveNames(projectId: string, names: string[]): void {
  try {
    window.localStorage.setItem(key(projectId), JSON.stringify(names))
  } catch {
    // storage blocked: the names still apply to this visit
  }
}

export function loadNames(projectId: string): string[] {
  try {
    const value: unknown = JSON.parse(window.localStorage.getItem(key(projectId)) ?? '[]')
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
  } catch {
    return []
  }
}
