import type { ScriptFormat } from '../../shared/events'
import { speakingLanguage } from '../../shared/languages'
import { DEFAULT_CHOICE, type TellingChoice } from './store'

/** The longest script the public demo takes (the server says so too, with the same number). */
export const MAX_SCRIPT_CHARS = 4000
export const SCRIPT_TYPES = '.txt,.md,.markdown,.fountain,text/plain,text/markdown'

const key = (projectId: string) => `frameteller.telling.${projectId}`

/** Kept per story in this browser: the studio starts the session the way the start screen chose. */
export function saveChoice(projectId: string, choice: TellingChoice): void {
  try {
    window.localStorage.setItem(key(projectId), JSON.stringify(choice))
  } catch {
    // storage blocked: the studio falls back to narrating
  }
}

export function loadChoice(projectId: string): TellingChoice {
  try {
    const raw = window.localStorage.getItem(key(projectId))
    const value: unknown = raw ? JSON.parse(raw) : null
    if (typeof value !== 'object' || value === null) return DEFAULT_CHOICE
    const v = value as Partial<TellingChoice>
    const mode = v.mode === 'teleprompter' || v.mode === 'read' ? v.mode : 'narrate'
    const format = v.format === 'markdown' || v.format === 'fountain' ? v.format : 'text'
    return {
      mode,
      script: typeof v.script === 'string' ? v.script : '',
      format,
      voice: typeof v.voice === 'string' ? v.voice : DEFAULT_CHOICE.voice,
      language: typeof v.language === 'string' ? v.language : DEFAULT_CHOICE.language,
      speaking: speakingLanguage(v.speaking),
    }
  } catch {
    return DEFAULT_CHOICE
  }
}

/** Fountain from its extension, or from screenplay scene headings in pasted text; Markdown from its extension. */
export function scriptFormat(text: string, fileName = ''): ScriptFormat {
  const name = fileName.toLowerCase()
  if (name.endsWith('.fountain')) return 'fountain'
  if (name.endsWith('.md') || name.endsWith('.markdown')) return 'markdown'
  if (/^(INT|EXT|INT\.\/EXT|I\/E)[. ]/m.test(text)) return 'fountain'
  return 'text'
}

/** Read an uploaded script, refusing what is not plain text. */
export async function readScriptFile(file: File): Promise<{ text: string; format: ScriptFormat }> {
  const name = file.name.toLowerCase()
  if (!/\.(txt|md|markdown|fountain)$/.test(name)) {
    throw new Error('Upload a .txt, .md or .fountain file. For Word documents, copy the text and paste it here.')
  }
  if (file.size > 64 * 1024) throw new Error(`That file is too long. Scripts can be up to ${MAX_SCRIPT_CHARS.toLocaleString('en-US')} characters.`)
  const text = await file.text()
  return { text, format: scriptFormat(text, file.name) }
}
