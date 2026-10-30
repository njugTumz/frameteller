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

/** How the store names one of a character's looks (ADR 0018): "wren/farmer_costume", as the API does. */
export function lookKey(characterId: string, lookId: string): string {
  return `${characterId}/${lookId}`
}

/** Whether a sheet is here: a character's everyday sheet, or one of its looks ("wren/farmer_costume"). */
function hasSheet(characters: Character[], key: string): boolean {
  const [id, lookId] = key.split('/')
  const c = characters.find((x) => x.id === id)
  if (!c) return false
  return lookId ? !!c.looks?.some((l) => l.id === lookId && l.reference_url) : !!c.reference_url
}

/** The sheets these shots need that are not here yet: new characters, and the looks they wear. */
function missingFor(characters: Character[], shots: Shot[]): string[] {
  const keys = shots.flatMap((s) => [...s.character_ids, ...Object.entries(s.looks ?? {}).map(([id, look]) => lookKey(id, look))])
  return keys.filter((k) => !hasSheet(characters, k))
}

function expectedFrom(state: CastState, shots: Shot[]): string[] {
  return [...new Set([...state.expected, ...missingFor(state.characters, shots)])]
}

function omit<T>(record: Record<string, T>, keys: Iterable<string>): Record<string, T> {
  const drop = new Set(keys)
  return Object.fromEntries(Object.entries(record).filter(([k]) => !drop.has(k)))
}

/** Apply one server event. Pure, so every event type is unit-tested. */
export function reduceCast(state: CastState, event: ServerEvent): CastState {
  switch (event.type) {
    case 'shot.created':
    case 'shot.updated': {
      const expected = expectedFrom(state, [event.shot])
      return expected.length === state.expected.length ? state : { ...state, expected, status: 'draft' }
    }
    case 'shots.replaced': {
      const expected = expectedFrom(state, event.shots)
      return expected.length === state.expected.length ? state : { ...state, expected, status: 'draft' }
    }
    case 'cast.proposed': {
      const characters = upsert(state.characters, event.characters)
      // Everything these characters now have a sheet for: their own, and each drawn look.
      const drawn = event.characters.flatMap((c) => [c.id, ...(c.looks ?? []).filter((l) => l.reference_url).map((l) => lookKey(c.id, l.id))])
      return {
        ...state,
        // New or redrawn sheets need a look before panels use them (ADR 0004).
        status: 'draft',
        characters,
        expected: state.expected.filter((key) => !hasSheet(characters, key)),
        redrawing: omit(state.redrawing, drawn),
        edits: omit(state.edits, drawn),
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
  return { ...next, expected: [...new Set(missingFor(cast.characters, shots))] }
}

export type ApprovalBlock = 'no-cast' | 'drawing' | 'missing-sheet' | null

/** Why the cast cannot be approved yet, if it cannot. */
export function approvalBlock(state: CastState): ApprovalBlock {
  if (state.characters.length === 0) return 'no-cast'
  if (state.drawing || state.expected.length > 0 || Object.keys(state.redrawing).length > 0) return 'drawing'
  if (state.characters.some((c) => !c.reference_url || c.looks?.some((l) => !l.reference_url))) return 'missing-sheet'
  return null
}

/** Whether a shot's panel can be drawn: the cast is approved and every character in it has the sheet of the look
 * they wear in it. */
export function castReadyFor(state: CastState, shot: Shot): boolean {
  if (state.status !== 'approved') return false
  const looks = Object.entries(shot.looks ?? {}).map(([id, look]) => lookKey(id, look))
  return [...shot.character_ids, ...looks].every((key) => hasSheet(state.characters, key) && !state.redrawing[key])
}

const words = (id: string) => id.replace(/[_-]+/g, ' ').trim()

/** "grey_cat" → "Grey cat", "wren/farmer_costume" → "Wren's farmer costume", for sheets not here yet. */
export function nameFromId(id: string): string {
  const [character = id, look] = id.split('/')
  const name = words(character)
  const capitalised = name.charAt(0).toUpperCase() + name.slice(1)
  return look ? `${capitalised}’s ${words(look)}` : capitalised
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
