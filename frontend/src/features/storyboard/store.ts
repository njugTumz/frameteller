import { create } from 'zustand'
import type { Project, Shot } from '../../shared/api/types'
import type { JobKind, JobStatus, ServerEvent } from '../../shared/events'

export interface PanelJob {
  kind: JobKind
  status: JobStatus
  revision: number | null
  message: string | null
}

export type SyncStatus = 'loading' | 'ready' | 'missing' | 'unreachable'

export interface StoryboardState {
  sync: SyncStatus
  projectId: string | null
  title: string
  style: Project['style']
  shots: Shot[]
  /** The latest panel job per shot (render or edit), from job.updated. */
  jobs: Record<string, PanelJob>
  /** Shots this browser asked to draw, so a draft is requested once. */
  requested: Record<string, true>
  /** A job finished: the project must be fetched again for the new image and masks. */
  stale: boolean
  loaded: boolean
}

export const initialStoryboard: StoryboardState = {
  sync: 'loading',
  projectId: null,
  title: '',
  style: 'pencil',
  shots: [],
  jobs: {},
  requested: {},
  stale: false,
  loaded: false,
}

const byNumber = (a: Shot, b: Shot) => a.number - b.number

function upsertShot(shots: Shot[], shot: Shot): Shot[] {
  const at = shots.findIndex((s) => s.id === shot.id)
  const next = at < 0 ? [...shots, shot] : shots.map((s, i) => (i === at ? { ...shot, panel: shot.panel ?? s.panel } : s))
  return next.sort(byNumber)
}

/** shots.replaced: the new shots take the removed ones' place, and every shot is renumbered 1..n. */
export function replaceShots(shots: Shot[], removed: string[], replacement: Shot[]): Shot[] {
  const gone = new Set(removed)
  const at = shots.findIndex((s) => gone.has(s.id))
  const kept = shots.filter((s) => !gone.has(s.id))
  const insertAt = at < 0 ? kept.length : shots.slice(0, at).filter((s) => !gone.has(s.id)).length
  const merged = [...kept.slice(0, insertAt), ...replacement, ...kept.slice(insertAt)]
  return merged.map((s, i) => (s.number === i + 1 ? s : { ...s, number: i + 1 }))
}

function omit<T>(record: Record<string, T>, keys: Iterable<string>): Record<string, T> {
  const drop = new Set(keys)
  return Object.fromEntries(Object.entries(record).filter(([k]) => !drop.has(k)))
}

const PANEL_JOBS: readonly JobKind[] = ['generate_panel', 'edit_panel']

/** Apply one server event. Pure, so every event type is unit-tested. */
export function reduceStoryboard(state: StoryboardState, event: ServerEvent): StoryboardState {
  switch (event.type) {
    case 'shot.created':
      return { ...state, shots: upsertShot(state.shots, event.shot) }
    case 'shots.replaced':
      return {
        ...state,
        shots: replaceShots(state.shots, event.removed_shot_ids, event.shots),
        jobs: omit(state.jobs, event.removed_shot_ids),
        requested: omit(state.requested, event.removed_shot_ids),
      }
    case 'job.updated': {
      if (!event.shot_id) return state
      if (event.kind === 'pre_segment_panel') return event.status === 'succeeded' ? { ...state, stale: true } : state
      if (!PANEL_JOBS.includes(event.kind)) return state
      const job: PanelJob = { kind: event.kind, status: event.status, revision: event.revision, message: event.message }
      const done = event.status === 'succeeded' || event.status === 'failed'
      return { ...state, jobs: { ...state.jobs, [event.shot_id]: job }, stale: state.stale || done }
    }
    default:
      return state
  }
}

/** A fresh copy of the project: shots and panels from the server win; finished jobs are forgotten. */
export function loadProject(state: StoryboardState, project: Project): StoryboardState {
  const jobs = Object.fromEntries(
    Object.entries(state.jobs).filter(([shotId, job]) => {
      const panel = project.shots.find((s) => s.id === shotId)?.panel
      if (job.status === 'failed') return true // keep the message until the next attempt
      if (job.status !== 'succeeded') return true
      return !panel || (job.revision !== null && panel.revision < job.revision)
    }),
  )
  return {
    ...state,
    projectId: project.id,
    title: project.title,
    style: project.style,
    shots: [...project.shots].sort(byNumber),
    jobs,
    stale: false,
    loaded: true,
    sync: 'ready',
  }
}

export type PanelPhase =
  | { kind: 'waiting-cast' }
  | { kind: 'queued' }
  | { kind: 'drawing'; what: 'draft' | 'final' | 'change' }
  | { kind: 'ready'; imageUrl: string; revision: number }
  | { kind: 'failed'; message: string }
  | { kind: 'not-drawn' }

/** What a shot card shows, from the shot, its latest job, and whether its cast is approved. */
export function panelPhase(shot: Shot, job: PanelJob | undefined, castReady: boolean, quality: 'draft' | 'final' = 'draft'): PanelPhase {
  const panel = shot.panel
  if (job?.status === 'queued') return { kind: 'queued' }
  if (job?.status === 'running' || (panel?.status === 'pending' && job?.status !== 'failed')) {
    return { kind: 'drawing', what: job?.kind === 'edit_panel' ? 'change' : quality }
  }
  if (job?.status === 'failed') return { kind: 'failed', message: job.message ?? 'This panel could not be drawn.' }
  if (panel?.status === 'ready' && panel.image_url) return { kind: 'ready', imageUrl: panel.image_url, revision: panel.revision }
  if (panel?.status === 'failed') return { kind: 'failed', message: 'This panel could not be drawn.' }
  return castReady ? { kind: 'not-drawn' } : { kind: 'waiting-cast' }
}

interface StoryboardActions {
  apply(event: ServerEvent): void
  load(project: Project): void
  markRequested(shotId: string, requested: boolean): void
  jobStarted(shotId: string, job: PanelJob): void
  setSync(sync: SyncStatus): void
  reset(): void
}

export const useStoryboardStore = create<StoryboardState & StoryboardActions>()((set) => ({
  ...initialStoryboard,
  apply: (event) => set((s) => reduceStoryboard(s, event)),
  load: (project) => set((s) => loadProject(s, project)),
  markRequested: (shotId, requested) =>
    set((s) => ({ requested: requested ? { ...s.requested, [shotId]: true } : omit(s.requested, [shotId]) })),
  jobStarted: (shotId, job) => set((s) => ({ jobs: { ...s.jobs, [shotId]: job } })),
  setSync: (sync) => set({ sync }),
  reset: () => set(initialStoryboard),
}))
