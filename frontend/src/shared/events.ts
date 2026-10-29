/**
 * The live session WebSocket contract, hand-written from docs/api-events.md (OpenAPI cannot describe it).
 * Nested objects reuse the REST schemas: the backend serialises them with the same DTOs.
 */
import type { Character, ReviewIssue, Shot, SupervisorEntry, Turn } from './api/types'

// ---- client → server ----

export type SessionMode = 'narrate' | 'co_direct' | 'teleprompter' | 'read'
export type ScriptFormat = 'text' | 'markdown' | 'fountain'

export interface StartMessage {
  mode: SessionMode
  keywords: string[]
  /** Keep the recording for the animatic's voice track. Only with the narrator's consent. */
  keep_audio: boolean
  /** Teleprompter and "Read it to me" (ADR 0015). */
  script?: string
  script_format?: ScriptFormat
  /** "Read it to me": a voice and a language locale from GET /voices. */
  voice?: string
  language?: string
}
export interface BeatMessage {
  type: 'beat'
}
export interface CorrectionMessage {
  type: 'transcript.corrected'
  turn_id: string
  text: string
}
export interface EndMessage {
  type: 'end'
}
/** "Read it to me": hold the reading before the next paragraph, or go on (also past an episode break). */
export interface ReadingMessage {
  type: 'pause' | 'continue'
}
export type ClientMessage = BeatMessage | CorrectionMessage | EndMessage | ReadingMessage

export const MAX_CORRECTION_CHARS = 2000
export const MAX_KEYWORDS = 50

// ---- server → client ----

export type JobKind =
  | 'generate_cast'
  | 'generate_panel'
  | 'pre_segment_panel'
  | 'edit_panel'
  | 'compose_panel'
  | 'export_animatic'
  | 'supervise_panel'
  | 'review_sheet'
export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export type ServerEvent =
  | { type: 'session.started'; mode: SessionMode }
  | { type: 'transcript.partial'; text: string }
  | { type: 'turn.completed'; turn: Turn }
  | { type: 'shot.created'; shot: Shot }
  | { type: 'shot.updated'; shot: Shot }
  | { type: 'shots.replaced'; turn: Turn; removed_shot_ids: string[]; shots: Shot[] }
  | { type: 'cast.proposed'; characters: Character[] }
  | {
      type: 'job.updated'
      kind: JobKind
      key: string
      status: JobStatus
      shot_id: string | null
      revision: number | null
      message: string | null
      /** 0–1 while an animatic export runs; null otherwise. */
      progress?: number | null
      /** Queued behind a capacity limit (ADR 0016): 1 is next, with an estimate in seconds. */
      position?: number | null
      estimate_s?: number | null
    }
  /** The studio is busy: this session waits in line before session.started (ADR 0016). */
  | { type: 'queue.waiting'; position: number; estimate_s: number }
  | { type: 'error'; message: string; fatal: boolean }
  | { type: 'audio.silent'; after_ms: number; level: number }
  | { type: 'session.ended'; turns: number; shots: number; heard?: boolean }
  // The continuity supervisor (ADR 0012): the project carries the badge; the entry is the feed's line.
  | { type: 'supervisor.reviewed'; entry: SupervisorEntry; revision: number | null }
  | { type: 'supervisor.fixed'; entry: SupervisorEntry; revision: number; fixes: number }
  | { type: 'supervisor.needs_user'; entry: SupervisorEntry; issues: ReviewIssue[]; fix_instruction: string; revision: number | null }
  // Scripts (ADR 0015). Paragraphs are counted from 0 through the whole script.
  | { type: 'script.accepted'; episodes: ScriptEpisode[] }
  | { type: 'teleprompter.advanced'; paragraph: number }
  | {
      type: 'script.voiced'
      paragraph: number
      episode: number
      text: string
      original: string
      audio_url: string
      duration_ms: number
    }
  | { type: 'script.paused'; next_paragraph: number; next_episode: number; reason: 'user' | 'episode' }
  | { type: 'script.resumed'; next_paragraph: number }

export interface ScriptParagraph {
  narration: string
  direction: string
}
export interface ScriptEpisode {
  number: number
  paragraphs: ScriptParagraph[]
}

export type ServerEventOf<T extends ServerEvent['type']> = Extract<ServerEvent, { type: T }>

/** Close codes from docs/api-events.md. */
export const CLOSE = { normal: 1000, policy: 1008, badStart: 4400, notFound: 4404, busy: 4409, paused: 4503 } as const

// ---- runtime guard ----

type Json = Record<string, unknown>

const isObj = (v: unknown): v is Json => typeof v === 'object' && v !== null && !Array.isArray(v)
const isStr = (v: unknown): v is string => typeof v === 'string'
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isStrOrNull = (v: unknown) => v === null || isStr(v)
const isNumOrNull = (v: unknown) => v === null || isNum(v)
const isStrArr = (v: unknown): v is string[] => Array.isArray(v) && v.every(isStr)

export function isTurn(v: unknown): v is Turn {
  return isObj(v) && isStr(v.id) && isStr(v.text) && isNum(v.start_ms) && isNum(v.end_ms) && isStrOrNull(v.speaker)
}

export function isShot(v: unknown): v is Shot {
  return (
    isObj(v) &&
    isStr(v.id) &&
    isNum(v.number) &&
    isStr(v.framing) &&
    isStrArr(v.character_ids) &&
    isStr(v.setting) &&
    isStr(v.action) &&
    isStr(v.dialogue) &&
    isNum(v.duration_ms) &&
    isStrArr(v.source_turn_ids) &&
    (v.panel === undefined || v.panel === null || isObj(v.panel))
  )
}

export function isCharacter(v: unknown): v is Character {
  return isObj(v) && isStr(v.id) && isStr(v.name) && isStr(v.description) && isStrOrNull(v.reference_url)
}

const JOB_KINDS: readonly string[] = [
  'generate_cast',
  'generate_panel',
  'pre_segment_panel',
  'edit_panel',
  'compose_panel',
  'export_animatic',
  'supervise_panel',
  'review_sheet',
]
const OUTCOMES: readonly string[] = ['checked', 'fixed', 'needs_user', 'accepted']

export function isSupervisorEntry(v: unknown): v is SupervisorEntry {
  return (
    isObj(v) &&
    isStr(v.at) &&
    isStr(v.subject) &&
    isStr(v.outcome) &&
    OUTCOMES.includes(v.outcome) &&
    isStr(v.message) &&
    isStrArr(v.rule_ids) &&
    isStr(v.model) &&
    isStrOrNull(v.shot_id) &&
    isStrOrNull(v.character_id)
  )
}

const isIssue = (v: unknown): v is ReviewIssue => isObj(v) && isStr(v.rule_id) && isStr(v.severity) && isStr(v.description)
const JOB_STATUSES: readonly string[] = ['queued', 'running', 'succeeded', 'failed']
const MODES: readonly string[] = ['narrate', 'co_direct', 'teleprompter', 'read']

const isParagraph = (v: unknown): v is ScriptParagraph => isObj(v) && isStr(v.narration) && isStr(v.direction)
const isEpisode = (v: unknown): v is ScriptEpisode =>
  isObj(v) && isNum(v.number) && Array.isArray(v.paragraphs) && v.paragraphs.every(isParagraph)

function check(e: Json): boolean {
  switch (e.type) {
    case 'session.started':
      return isStr(e.mode) && MODES.includes(e.mode)
    case 'transcript.partial':
      return isStr(e.text)
    case 'turn.completed':
      return isTurn(e.turn)
    case 'shot.created':
    case 'shot.updated':
      return isShot(e.shot)
    case 'shots.replaced':
      return isTurn(e.turn) && isStrArr(e.removed_shot_ids) && Array.isArray(e.shots) && e.shots.every(isShot)
    case 'cast.proposed':
      return Array.isArray(e.characters) && e.characters.every(isCharacter)
    case 'job.updated':
      return (
        isStr(e.kind) &&
        JOB_KINDS.includes(e.kind) &&
        isStr(e.key) &&
        isStr(e.status) &&
        JOB_STATUSES.includes(e.status) &&
        isStrOrNull(e.shot_id) &&
        isNumOrNull(e.revision) &&
        isStrOrNull(e.message) &&
        (e.progress === undefined || isNumOrNull(e.progress)) &&
        (e.position === undefined || isNumOrNull(e.position)) &&
        (e.estimate_s === undefined || isNumOrNull(e.estimate_s))
      )
    case 'queue.waiting':
      return typeof e.position === 'number' && typeof e.estimate_s === 'number'
    case 'error':
      return isStr(e.message) && typeof e.fatal === 'boolean'
    case 'audio.silent':
      return isNum(e.after_ms) && isNum(e.level)
    case 'session.ended':
      return isNum(e.turns) && isNum(e.shots) && (e.heard === undefined || typeof e.heard === 'boolean')
    case 'supervisor.reviewed':
      return isSupervisorEntry(e.entry) && isNumOrNull(e.revision)
    case 'supervisor.fixed':
      return isSupervisorEntry(e.entry) && isNum(e.revision) && isNum(e.fixes)
    case 'supervisor.needs_user':
      return (
        isSupervisorEntry(e.entry) &&
        Array.isArray(e.issues) &&
        e.issues.every(isIssue) &&
        isStr(e.fix_instruction) &&
        isNumOrNull(e.revision)
      )
    case 'script.accepted':
      return Array.isArray(e.episodes) && e.episodes.every(isEpisode)
    case 'teleprompter.advanced':
      return isNum(e.paragraph)
    case 'script.voiced':
      return (
        isNum(e.paragraph) &&
        isNum(e.episode) &&
        isStr(e.text) &&
        isStr(e.original) &&
        isStr(e.audio_url) &&
        isNum(e.duration_ms)
      )
    case 'script.paused':
      return isNum(e.next_paragraph) && isNum(e.next_episode) && (e.reason === 'user' || e.reason === 'episode')
    case 'script.resumed':
      return isNum(e.next_paragraph)
    default:
      return false // unknown types are ignored, as the backend's own clients do
  }
}

/** Parse one WebSocket text frame. Malformed or unknown messages return null. */
export function parseServerEvent(raw: unknown): ServerEvent | null {
  if (!isStr(raw)) return null
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return null
  }
  return isObj(value) && check(value) ? (value as ServerEvent) : null
}
