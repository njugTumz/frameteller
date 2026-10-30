import { create } from 'zustand'
import type { ScriptEpisode, ScriptFormat, ServerEvent } from '../../shared/events'

/** How the story is told (ADR 0015): out loud, read from a script, or read aloud by a voice. */
export type TellingMode = 'narrate' | 'teleprompter' | 'read'

/** "Read it to me": reading → paused by the listener, or waiting at an episode break for its drafts. */
export type Reading = 'idle' | 'reading' | 'paused' | 'episode-break' | 'done'

export interface VoicedClip {
  paragraph: number
  episode: number
  text: string
  original: string
  audioUrl: string
  durationMs: number
}

export interface ScriptState {
  mode: TellingMode
  /** The paragraphs as the server split them (script.accepted), in order through every episode. */
  episodes: ScriptEpisode[]
  /** Teleprompter: the paragraph being read now, counted from 0 through the script. */
  current: number
  reading: Reading
  /** Synthesized paragraphs, in order: the browser plays them one after the other. */
  clips: VoicedClip[]
  /** The episode that comes after a break: "Episode 2 is next". */
  nextEpisode: number | null
}

export const initialScript: ScriptState = {
  mode: 'narrate',
  episodes: [],
  current: 0,
  reading: 'idle',
  clips: [],
  nextEpisode: null,
}

export interface Paragraph {
  index: number
  episode: number
  narration: string
  direction: string
}

/** Every paragraph with its place in the script and its episode. */
export function paragraphs(episodes: ScriptEpisode[]): Paragraph[] {
  let index = 0
  return episodes.flatMap((e) => e.paragraphs.map((p) => ({ index: index++, episode: e.number, ...p })))
}

/** Apply one server event. Pure, so every event type is unit-tested. */
export function reduceScript(state: ScriptState, event: ServerEvent): ScriptState {
  switch (event.type) {
    case 'session.started':
      return event.mode === 'read' ? { ...state, reading: 'reading', clips: [], nextEpisode: null } : state
    case 'script.accepted':
      return { ...state, episodes: event.episodes, current: 0 }
    case 'teleprompter.advanced':
      return { ...state, current: event.paragraph }
    case 'script.voiced': {
      const clip: VoicedClip = {
        paragraph: event.paragraph,
        episode: event.episode,
        text: event.text,
        original: event.original,
        audioUrl: event.audio_url,
        durationMs: event.duration_ms,
      }
      return { ...state, clips: [...state.clips.filter((c) => c.paragraph !== clip.paragraph), clip] }
    }
    case 'script.paused':
      return event.reason === 'episode'
        ? { ...state, reading: 'episode-break', nextEpisode: event.next_episode }
        : { ...state, reading: 'paused' }
    case 'script.resumed':
      return { ...state, reading: 'reading', nextEpisode: null }
    case 'session.ended':
      return state.reading === 'idle' ? state : { ...state, reading: 'done', nextEpisode: null }
    default:
      return state
  }
}

interface ScriptActions {
  apply(event: ServerEvent): void
  set(patch: Partial<ScriptState>): void
  reset(): void
}

export const useScriptStore = create<ScriptState & ScriptActions>()((set) => ({
  ...initialScript,
  apply: (event) => set((s) => reduceScript(s, event)),
  set: (patch) => set(patch),
  reset: () => set(initialScript),
}))

/** What the start screen chose for a story, kept in this browser so the studio can start the session. */
export interface TellingChoice {
  mode: TellingMode
  script: string
  format: ScriptFormat
  voice: string
  language: string
}

export const DEFAULT_VOICE = 'en-US-AvaMultilingualNeural'
export const DEFAULT_CHOICE: TellingChoice = { mode: 'narrate', script: '', format: 'text', voice: DEFAULT_VOICE, language: 'en-US' }
