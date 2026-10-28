import { create } from 'zustand'
import type { Character, Project, Shot } from '../../shared/api/types'
import type { ServerEvent } from '../../shared/events'

export interface CastState {
  status: 'draft' | 'approved'
  characters: Character[]
  /** Character ids the director has used whose sheets are not here yet. */
  expected: string[]
  /** Descriptions the user has edited and not yet sent, by id. */
  edits: Record<string, string>
  /** Sheets being drawn again (a regenerate, or an edited description). */
  redrawing: Record<string, true>
  /** A reference-sheet job is queued or running. */
  drawing: boolean
  approving: boolean
  /** A rename, remove or merge is on its way. */
  managing: boolean
  error: string | null
}

export const initialCast: CastState = {
  status: 'draft',
  characters: [],
  expected: [],
  edits: {},
  redrawing: {},
  drawing: false,
  approving: false,
  managing: false,
  error: null,
}

function upsert(list: Character[], incoming: Character[]): Character[] {
  const next = [...list]
  for (const c of incoming) {
    const at = next.findIndex((x) => x.id === c.id)
    if (at < 0) next.push(c)
    else next[at] = c
  }
  return next
}

function expectedFrom(state: CastState, shots: Shot[]): string[] {
  const known = new Set(state.characters.map((c) => c.id))
  const ids = shots.flatMap((s) => s.character_ids).filter((id) => !known.has(id))
  return [...new Set([...state.expected, ...ids])]
}

function omit<T>(record: Record<string, T>, keys: Iterable<string>): Record<string, T> {
  const drop = new Set(keys)
  return Object.fromEntries(Object.entries(record).filter(([k]) => !drop.has(k)))
}

/** Apply one server event. Pure, so every event type is unit-tested. */
export function reduceCast(state: CastState, event: ServerEvent): CastState {
  switch (event.type) {
    case 'shot.created': {
      const expected = expectedFrom(state, [event.shot])
      return expected.length === state.expected.length ? state : { ...state, expected, status: 'draft' }
    }
    case 'shots.replaced': {
      const expected = expectedFrom(state, event.shots)
      return expected.length === state.expected.length ? state : { ...state, expected, status: 'draft' }
    }
    case 'cast.proposed': {
      const ids = event.characters.map((c) => c.id)
      return {
        ...state,
        // New or redrawn sheets need a look before panels use them (ADR 0004).
        status: 'draft',
        characters: upsert(state.characters, event.characters),
        expected: state.expected.filter((id) => !ids.includes(id)),
        redrawing: omit(state.redrawing, ids),
        edits: omit(state.edits, ids),
      }
    }
    case 'job.updated':
      if (event.kind !== 'generate_cast') return state
      if (event.status === 'queued' || event.status === 'running') return { ...state, drawing: true, error: null }
      if (event.status === 'failed') return { ...state, drawing: false, redrawing: {}, error: event.message ?? 'A reference sheet could not be drawn. Regenerate it to try again.' }
      return { ...state, drawing: false }
    default:
      return state
  }
}

export function loadCast(state: CastState, cast: Project['cast'], shots: Project['shots']): CastState {
  const next = { ...state, status: cast.status === 'approved' ? ('approved' as const) : ('draft' as const), characters: cast.characters }
  const known = new Set(cast.characters.map((c) => c.id))
  return { ...next, expected: [...new Set(shots.flatMap((s) => s.character_ids))].filter((id) => !known.has(id)) }
}

export type ApprovalBlock = 'no-cast' | 'drawing' | 'missing-sheet' | null

/** Why the cast cannot be approved yet, if it cannot. */
export function approvalBlock(state: CastState): ApprovalBlock {
  if (state.characters.length === 0) return 'no-cast'
  if (state.drawing || state.expected.length > 0 || Object.keys(state.redrawing).length > 0) return 'drawing'
  if (state.characters.some((c) => !c.reference_url)) return 'missing-sheet'
  return null
}

/** Whether a shot's panel can be drawn: the cast is approved and every character in it has its sheet. */
export function castReadyFor(state: CastState, shot: Shot): boolean {
  if (state.status !== 'approved') return false
  return shot.character_ids.every((id) => state.characters.some((c) => c.id === id && c.reference_url) && !state.redrawing[id])
}

/** "grey_cat" → "Grey cat", for characters whose sheets have not arrived yet. */
export function nameFromId(id: string): string {
  const words = id.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

interface CastActions {
  apply(event: ServerEvent): void
  load(project: Project): void
  edit(id: string, description: string): void
  set(patch: Partial<CastState>): void
  reset(): void
}

export const useCastStore = create<CastState & CastActions>()((set) => ({
  ...initialCast,
  apply: (event) => set((s) => reduceCast(s, event)),
  load: (project) => set((s) => loadCast(s, project.cast, project.shots)),
  edit: (id, description) => set((s) => ({ edits: { ...s.edits, [id]: description } })),
  set: (patch) => set(patch),
  reset: () => set(initialCast),
}))
