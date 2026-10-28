import { create } from 'zustand'
import type { Mask } from '../../shared/api/types'

/** A canvas geometry edit of one cut-out, in full-size panel pixels (ADR 0005). No model call. */
export interface Move {
  dx: number
  dy: number
  scale: number
}

export const NO_MOVE: Move = { dx: 0, dy: 0, scale: 1 }

export interface Snapshot {
  imageUrl: string
  revision: number
}

export interface EditorState {
  shotId: string | null
  /** The panel revision the selection and moves belong to; a new revision clears them. */
  revision: number | null
  selecting: boolean
  selection: { mask: Mask; cached: boolean; ms: number } | null
  selectError: string | null
  /** Moves per "shotId:revision", then per mask id. Kept in this browser. */
  moves: Record<string, Record<string, Move>>
  instruction: string
  dictation: 'idle' | 'recording' | 'transcribing'
  sending: boolean
  editError: string | null
  /** The panel as it was before the last edit or final render, for before/after. */
  before: Snapshot | null
  showBefore: boolean
}

export const initialEditor: EditorState = {
  shotId: null,
  revision: null,
  selecting: false,
  selection: null,
  selectError: null,
  moves: {},
  instruction: '',
  dictation: 'idle',
  sending: false,
  editError: null,
  before: null,
  showBefore: false,
}

export const moveKey = (shotId: string, revision: number) => `${shotId}:${revision}`

/** Clamp a resize so a cut-out stays usable: between a fifth and three times its size. */
export function clampMove(move: Move): Move {
  return { dx: Math.round(move.dx), dy: Math.round(move.dy), scale: Math.min(3, Math.max(0.2, Number(move.scale.toFixed(3)))) }
}

/** Preview pixels → full-size panel pixels, the way the backend maps a click (scale, round down, clamp). */
export function toPanelPoint(x: number, y: number, preview: { width: number; height: number }, panel: { width: number; height: number }) {
  const px = Math.min(panel.width - 1, Math.max(0, Math.floor((x * panel.width) / preview.width)))
  const py = Math.min(panel.height - 1, Math.max(0, Math.floor((y * panel.height) / preview.height)))
  return { x: px, y: py }
}

/** The smallest cached mask whose box holds the point (panel pixels): shown at once while the server confirms. */
export function cachedMaskAt(masks: Mask[], point: { x: number; y: number }): Mask | null {
  const inside = masks.filter((m) => point.x >= m.box.left && point.x < m.box.right && point.y >= m.box.top && point.y < m.box.bottom)
  const area = (m: Mask) => (m.box.right - m.box.left) * (m.box.bottom - m.box.top)
  return inside.sort((a, b) => area(a) - area(b))[0] ?? null
}

/** The instruction as sent: it names the selected object when the user did not, so the edit lands on it. */
export function instructionFor(text: string, selected: Mask | null): string {
  const said = text.trim()
  if (!selected || said.toLowerCase().includes(selected.label.toLowerCase())) return said
  return `${said} (the ${selected.label})`
}

interface EditorActions {
  open(shotId: string, revision: number | null): void
  close(): void
  /** The panel shown changed revision (an edit or a final finished): selection belongs to the old one. */
  revisionChanged(revision: number | null): void
  set(patch: Partial<EditorState>): void
  setMove(shotId: string, revision: number, maskId: string, move: Move): void
  resetMoves(shotId: string, revision: number): void
}

export const useEditorStore = create<EditorState & EditorActions>()((set) => ({
  ...initialEditor,
  open: (shotId, revision) =>
    set((s) => ({ ...initialEditor, moves: s.moves, shotId, revision, before: s.shotId === shotId ? s.before : null })),
  close: () => set((s) => ({ ...initialEditor, moves: s.moves, before: s.before, shotId: null })),
  revisionChanged: (revision) =>
    set((s) => (s.revision === revision ? s : { revision, selection: null, selectError: null, showBefore: false })),
  set: (patch) => set(patch),
  setMove: (shotId, revision, maskId, move) =>
    set((s) => {
      const key = moveKey(shotId, revision)
      return { moves: { ...s.moves, [key]: { ...s.moves[key], [maskId]: clampMove(move) } } }
    }),
  resetMoves: (shotId, revision) =>
    set((s) => {
      const { [moveKey(shotId, revision)]: _gone, ...rest } = s.moves
      return { moves: rest }
    }),
}))
