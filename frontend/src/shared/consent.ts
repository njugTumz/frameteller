/** "Keep my narration for the animatic": the narrator's choice per story, in this browser. On by default. */
const key = (projectId: string) => `frameteller.keepAudio.${projectId}`

export function saveKeepAudio(projectId: string, keep: boolean): void {
  try {
    window.localStorage.setItem(key(projectId), keep ? '1' : '0')
  } catch {
    // storage blocked: the default (keep) applies
  }
}

export function loadKeepAudio(projectId: string): boolean {
  try {
    return window.localStorage.getItem(key(projectId)) !== '0'
  } catch {
    return true
  }
}
