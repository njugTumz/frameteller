import { create } from 'zustand'
import type { Turn } from '../../shared/api/types'
import type { ServerEvent } from '../../shared/events'

/** Where the narration is: idle → mic → connecting → live → finishing → ended (and back to idle to tell more). */
export type Telling = 'idle' | 'mic' | 'connecting' | 'live' | 'finishing' | 'ended'

export type ProblemKind = 'mic-blocked' | 'mic-missing' | 'mic-busy' | 'mic-unsupported' | 'mic-lost' | 'connection' | 'server'

export interface Problem {
  kind: ProblemKind
  message: string
}

export interface RecordingState {
  telling: Telling
  /** Words heard since the last completed turn. Replaced, never appended (docs/api-events.md). */
  partial: string
  /** Completed beats (or transcriber turns), in order. */
  turns: Turn[]
  /** Corrections sent and not yet applied, by turn id. */
  correcting: Record<string, 'sending' | 'failed'>
  beats: number
  level: number
  problem: Problem | null
  /** Non-fatal messages from the server or the browser, newest last. */
  notices: string[]
  /** Names that bias recognition (characters and places). Fixed for a session. */
  keywords: string[]
  /** A session socket is open, so job updates arrive as events (otherwise the storyboard polls). */
  connected: boolean
  /** Send keep_audio: the narrator agreed to keep the recording for the animatic. */
  keepAudio: boolean
  /** The server heard 8 s of near-silence and no words (audio.silent): probably the wrong microphone. */
  silent: boolean
  /** The last session ended without a single word heard. */
  heardNothing: boolean
  /** The microphone in use, as the browser names it. */
  micLabel: string
  /** The microphone the narrator picked; null means the system default. */
  deviceId: string | null
  /** The session socket dropped unexpectedly (usually a new studio version going live) and the project is
   * being fetched again: "Updating the studio, your work is safe". */
  updating: boolean
  /** The studio is busy and this session waits in line (queue.waiting, ADR 0016); null once it starts. */
  queue: { position: number; estimateS: number } | null
}

export const initialRecording: RecordingState = {
  telling: 'idle',
  partial: '',
  turns: [],
  correcting: {},
  beats: 0,
  level: 0,
  problem: null,
  notices: [],
  keywords: [],
  connected: false,
  keepAudio: true,
  silent: false,
  heardNothing: false,
  micLabel: '',
  deviceId: null,
  updating: false,
  queue: null,
}

const MAX_NOTICES = 3

export function withNotice(notices: string[], message: string): string[] {
  return [...notices.filter((n) => n !== message), message].slice(-MAX_NOTICES)
}

function upsertTurn(turns: Turn[], turn: Turn): Turn[] {
  const at = turns.findIndex((t) => t.id === turn.id)
  if (at < 0) return [...turns, turn]
  return turns.map((t, i) => (i === at ? turn : t))
}

function without<T>(record: Record<string, T>, key: string): Record<string, T> {
  const { [key]: _gone, ...rest } = record
  return rest
}

/** Apply one server event. Pure, so every event type is unit-tested. */
export function reduceRecording(state: RecordingState, event: ServerEvent): RecordingState {
  switch (event.type) {
    case 'session.started':
      return { ...state, telling: state.telling === 'finishing' ? 'finishing' : 'live', problem: null, heardNothing: false, queue: null }
    case 'queue.waiting':
      return { ...state, queue: { position: event.position, estimateS: event.estimate_s } }
    case 'transcript.partial':
      return { ...state, partial: event.text, silent: state.silent && !event.text.trim() }
    case 'audio.silent':
      return { ...state, silent: true }
    case 'turn.completed':
      return { ...state, turns: upsertTurn(state.turns, event.turn) }
    case 'shots.replaced':
      return { ...state, turns: upsertTurn(state.turns, event.turn), correcting: without(state.correcting, event.turn.id) }
    case 'error': {
      if (event.fatal) return { ...state, problem: { kind: 'server', message: event.message }, telling: 'idle', level: 0, queue: null }
      const correcting = Object.fromEntries(
        Object.entries(state.correcting).map(([id, s]) => [id, s === 'sending' && /correct/i.test(event.message) ? 'failed' : s]),
      )
      return { ...state, notices: withNotice(state.notices, event.message), correcting }
    }
    case 'session.ended':
      return { ...state, telling: 'ended', partial: '', level: 0, silent: false, heardNothing: event.heard === false }
    default:
      return state
  }
}

interface RecordingActions {
  apply(event: ServerEvent): void
  setTelling(telling: Telling): void
  setLevel(level: number): void
  beatSent(): void
  correctionSent(turnId: string): void
  setProblem(problem: Problem | null): void
  notice(message: string): void
  dismissNotice(message: string): void
  setKeywords(keywords: string[]): void
  setConnected(connected: boolean): void
  set(patch: Partial<RecordingState>): void
  /** Load the turns of a project opened again. */
  loadTurns(turns: Turn[]): void
  reset(): void
}

export const useRecordingStore = create<RecordingState & RecordingActions>()((set) => ({
  ...initialRecording,
  apply: (event) => set((s) => reduceRecording(s, event)),
  setTelling: (telling) => set((s) => ({ telling, level: telling === 'live' ? s.level : 0, partial: telling === 'idle' ? '' : s.partial })),
  setLevel: (level) => set({ level }),
  beatSent: () => set((s) => ({ beats: s.beats + 1 })),
  correctionSent: (turnId) => set((s) => ({ correcting: { ...s.correcting, [turnId]: 'sending' } })),
  setProblem: (problem) => set({ problem }),
  notice: (message) => set((s) => ({ notices: withNotice(s.notices, message) })),
  dismissNotice: (message) => set((s) => ({ notices: s.notices.filter((n) => n !== message) })),
  setKeywords: (keywords) => set({ keywords }),
  setConnected: (connected) => set({ connected }),
  set: (patch) => set(patch),
  loadTurns: (turns) => set({ turns }),
  reset: () => set(initialRecording),
}))
