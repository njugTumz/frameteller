/**
 * The live session WebSocket contract, hand-written from docs/api-events.md (OpenAPI cannot describe it).
 * Nested objects reuse the REST schemas: the backend serialises them with the same DTOs.
 */
import type { Character, ReviewIssue, Shot, SupervisorEntry, Turn } from './api/types'

// ---- client → server ----

export type SessionMode = 'narrate' | 'co_direct'

export interface StartMessage {
  mode: SessionMode
  keywords: string[]
  /** Keep the recording for the animatic's voice track. Only with the narrator's consent. */
  keep_audio: boolean
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
export type ClientMessage = BeatMessage | CorrectionMessage | EndMessage

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
    }
  | { type: 'error'; message: string; fatal: boolean }
  | { type: 'audio.silent'; after_ms: number; level: number }
  | { type: 'session.ended'; turns: number; shots: number; heard?: boolean }
  // The continuity supervisor (ADR 0012): the project carries the badge; the entry is the feed's line.
  | { type: 'supervisor.reviewed'; entry: SupervisorEntry; revision: number | null }
  | { type: 'supervisor.fixed'; entry: SupervisorEntry; revision: number; fixes: number }
  | { type: 'supervisor.needs_user'; entry: SupervisorEntry; issues: ReviewIssue[]; fix_instruction: string; revision: number | null }

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

function check(e: Json): boolean {
  switch (e.type) {
    case 'session.started':
      return e.mode === 'narrate' || e.mode === 'co_direct'
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
        (e.progress === undefined || isNumOrNull(e.progress))
      )
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
