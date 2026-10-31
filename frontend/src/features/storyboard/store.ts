import { create } from 'zustand'
import type { Animatic, Narration, Project, Shot, SupervisorEntry } from '../../shared/api/types'
import type { JobKind, JobStatus, ServerEvent } from '../../shared/events'

export interface PanelJob {
  kind: JobKind
  status: JobStatus
  revision: number | null
  message: string | null
  /** The job's idempotency key, to ask GET /projects/{id}/jobs/{key} when its events stop. */
  key?: string
  /** Waiting behind the studio's limits (ADR 0016): its place in line and an estimate in seconds. */
  position?: number | null
  estimateS?: number | null
}

export type SyncStatus = 'loading' | 'ready' | 'missing' | 'unreachable'

/** The animatic export job, from job.updated: progress is 0–1 while it runs. */
export interface ExportJob {
  status: JobStatus
  progress: number | null
  message: string | null
  key?: string
  /** The animatic URL when the export started: a different one in the project means it finished. */
  from?: string | null
  /** Waiting for a free renderer (ADR 0016). */
  position?: number | null
  estimateS?: number | null
}

/** A job the server no longer knows (it ran on a revision that was replaced) and whose result never arrived. */
export const EXPORT_INTERRUPTED = 'The export stopped while the studio was updating. Export again.'
export const DRAW_INTERRUPTED = 'Drawing stopped while the studio was updating. Draw it again.'

/** What a job status check says: the server's statuses, plus unknown for a job it never saw. */
export type ResolvedStatus = JobStatus | 'unknown'

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
  /** Saved moves being composited on a clean plate (compose_panel), per shot (ADR 0010). */
  composing: Record<string, JobStatus>
  /** The compose_panel job key per shot, for the job status fallback. */
  composingKeys: Record<string, string>
  /** When the last job.updated arrived or a job was queued (ms since epoch): 20 s of silence triggers a check. */
  lastJobAt: number
  /** The latest animatic export job, if one ran in this visit. */
  exportJob: ExportJob | null
  animatic: Animatic | null
  narrations: Narration[]
  shareToken: string | null
  /** The share page may be indexed by search engines; otherwise it is unlisted. */
  sharePublic: boolean
  /** The continuity supervisor checks every sheet and render (the project setting, ADR 0012). */
  continuityChecks: boolean
  /** The supervisor's decisions, oldest first, as the project has them. */
  supervisor: SupervisorEntry[]
  /**
   * Shots whose new render the supervisor has not reported on yet, with when the render finished (ms). Its
   * events may come after the session socket closed, so the project is polled for a while (REVIEW_WAIT_MS).
   */
  awaitingReview: Record<string, number>
  /**
   * Shots this page asked to Redraw, with the revision shown when it asked (ADR 0022). Once the new drawing is
   * in, the card offers Use new / Keep previous until one is chosen.
   */
  redraws: Record<string, number>
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
  composing: {},
  composingKeys: {},
  lastJobAt: 0,
  exportJob: null,
  animatic: null,
  narrations: [],
  shareToken: null,
  sharePublic: false,
  continuityChecks: true,
  supervisor: [],
  awaitingReview: {},
  redraws: {},
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
/** How long a finished render waits for its review before the studio stops polling for it. */
export const REVIEW_WAIT_MS = 90_000

/** Apply one server event. Pure (the clock is a parameter), so every event type is unit-tested. */
export function reduceStoryboard(state: StoryboardState, event: ServerEvent, now = Date.now()): StoryboardState {
  switch (event.type) {
    case 'supervisor.reviewed':
    case 'supervisor.fixed':
    case 'supervisor.needs_user': {
      // The badge and the fixed image are on the project: fetch it again. The feed line shows at once.
      const shot = event.entry.shot_id
      const seen = state.supervisor.some((e) => e.at === event.entry.at && e.message === event.entry.message)
      return {
        ...state,
        supervisor: seen ? state.supervisor : [...state.supervisor, event.entry],
        awaitingReview: shot ? omit(state.awaitingReview, [shot]) : state.awaitingReview,
        stale: true,
      }
    }
    case 'shot.created':
      return { ...state, shots: upsertShot(state.shots, event.shot) }
    case 'shot.updated': {
      // A reveal changed who or what the shot shows: its panel is now out of date. The cast may have lost a
      // guessed character, so the project is fetched again.
      const old = state.shots.find((s) => s.id === event.shot.id)?.panel
      const panel = old ? { ...old, outdated: true } : event.shot.panel
      return { ...state, shots: upsertShot(state.shots, { ...event.shot, panel }), stale: true }
    }
    case 'shots.replaced':
      return {
        ...state,
        shots: replaceShots(state.shots, event.removed_shot_ids, event.shots),
        jobs: omit(state.jobs, event.removed_shot_ids),
        requested: omit(state.requested, event.removed_shot_ids),
        redraws: omit(state.redraws, event.removed_shot_ids),
      }
    case 'job.updated': {
      const done = event.status === 'succeeded' || event.status === 'failed'
      if (event.kind === 'export_animatic') {
        const exportJob: ExportJob = {
          ...state.exportJob,
          status: event.status,
          progress: event.progress ?? state.exportJob?.progress ?? null,
          message: event.message,
          key: event.key,
          position: event.position ?? null,
          estimateS: event.estimate_s ?? null,
        }
        return { ...state, exportJob, stale: state.stale || event.status === 'succeeded' }
      }
      // A failed sheet: the project has the character, with why it failed; fetch it so the card can say so.
      if (event.kind === 'generate_cast') return event.status === 'failed' ? { ...state, stale: true } : state
      if (!event.shot_id) return state
      if (event.kind === 'compose_panel') {
        return {
          ...state,
          composing: { ...state.composing, [event.shot_id]: event.status },
          composingKeys: { ...state.composingKeys, [event.shot_id]: event.key },
          stale: state.stale || done,
        }
      }
      if (event.kind === 'pre_segment_panel') return event.status === 'succeeded' ? { ...state, stale: true } : state
      if (!PANEL_JOBS.includes(event.kind)) return state
      const job: PanelJob = {
        kind: event.kind,
        status: event.status,
        revision: event.revision,
        message: event.message,
        key: event.key,
        position: event.position ?? null,
        estimateS: event.estimate_s ?? null,
      }
      const awaitingReview =
        event.status === 'succeeded' && state.continuityChecks ? { ...state.awaitingReview, [event.shot_id]: now } : state.awaitingReview
      return { ...state, jobs: { ...state.jobs, [event.shot_id]: job }, awaitingReview, stale: state.stale || done }
    }
    default:
      return state
  }
}

const inFlight = (status: JobStatus | undefined) => status === 'queued' || status === 'running'

/** Work this page is waiting for: a job.updated (or a supervisor event) should arrive for each. */
export function hasJobsInFlight(state: StoryboardState, now = Date.now()): boolean {
  return (
    Object.values(state.awaitingReview).some((since) => now - since < REVIEW_WAIT_MS) ||
    inFlight(state.exportJob?.status) ||
    Object.values(state.composing).some(inFlight) ||
    Object.values(state.jobs).some((j) => inFlight(j.status)) ||
    state.shots.some((s) => s.panel?.status === 'pending')
  )
}

/** Keys of in-flight jobs whose status can be asked for. */
export function inFlightKeys(state: StoryboardState): string[] {
  const keys = [
    inFlight(state.exportJob?.status) ? state.exportJob?.key : undefined,
    ...Object.entries(state.composing).map(([shot, status]) => (inFlight(status) ? state.composingKeys[shot] : undefined)),
    ...Object.values(state.jobs).map((j) => (inFlight(j.status) ? j.key : undefined)),
  ]
  return keys.filter((k): k is string => !!k)
}

/**
 * GET /jobs/{key} answered for a job whose events were missed. Unknown means the server that ran it was
 * replaced: what it finished is already in the fetched project, and anything else stopped.
 */
export function resolveJob(state: StoryboardState, key: string, status: ResolvedStatus, message: string | null): StoryboardState {
  if (status === 'queued' || status === 'running') return state
  const failed = status === 'failed' || status === 'unknown'
  if (state.exportJob?.key === key && inFlight(state.exportJob.status)) {
    const exportJob: ExportJob = failed
      ? { ...state.exportJob, status: 'failed', message: message ?? EXPORT_INTERRUPTED }
      : { ...state.exportJob, status: 'succeeded', progress: 1 }
    return { ...state, exportJob, stale: state.stale || !failed }
  }
  const shot = Object.entries(state.composingKeys).find(([, k]) => k === key)?.[0]
  if (shot && inFlight(state.composing[shot])) {
    // A lost compose leaves the panel as the project shows it; moving again composes again.
    return { ...state, composing: omit(state.composing, [shot]), stale: true }
  }
  const panelShot = Object.entries(state.jobs).find(([, j]) => j.key === key && inFlight(j.status))?.[0]
  if (panelShot) {
    const job = state.jobs[panelShot]
    if (!job) return state
    const next: PanelJob = failed ? { ...job, status: 'failed', message: message ?? DRAW_INTERRUPTED } : { ...job, status: 'succeeded' }
    return { ...state, jobs: { ...state.jobs, [panelShot]: next }, stale: true }
  }
  return state
}

/** A fresh copy of the project: shots and panels from the server win; finished jobs are forgotten. */
export function loadProject(state: StoryboardState, project: Project, now = Date.now()): StoryboardState {
  const checks = project.continuity_checks ?? true
  const awaitingReview: Record<string, number> = {}
  for (const shot of project.shots) {
    const panel = shot.panel
    if (!checks || panel?.status !== 'ready' || panel.review) continue
    const job = state.jobs[shot.id]
    // A render this page waited for has finished (seen here, not through an event): its review comes next.
    const finished = job && job.status !== 'failed' && job.revision !== null && panel.revision >= job.revision
    const since = state.awaitingReview[shot.id] ?? (finished ? now : undefined)
    if (since !== undefined && now - since < REVIEW_WAIT_MS) awaitingReview[shot.id] = since
  }
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
    // A finished composite is in the project now; one still running keeps its badge.
    composing: Object.fromEntries(Object.entries(state.composing).filter(([, status]) => status === 'queued' || status === 'running')),
    // The export finished while its events were missed (a dropped socket): the project has the new animatic.
    exportJob:
      state.exportJob && inFlight(state.exportJob.status) && project.animatic && project.animatic.url !== state.exportJob.from
        ? { ...state.exportJob, status: 'succeeded', progress: 1 }
        : state.exportJob,
    animatic: project.animatic,
    narrations: project.narrations,
    shareToken: project.share_token,
    sharePublic: project.share_public,
    continuityChecks: checks,
    supervisor: project.supervisor ?? [],
    awaitingReview,
    stale: false,
    loaded: true,
    sync: 'ready',
  }
}

export type PanelPhase =
  | { kind: 'waiting-cast' }
  | { kind: 'queued'; position?: number; estimateS?: number; previousUrl?: string }
  | { kind: 'drawing'; what: 'draft' | 'final' | 'change'; previousUrl?: string }
  | { kind: 'ready'; imageUrl: string; revision: number; outdated: boolean }
  | { kind: 'failed'; message: string; previousUrl?: string; suggestion?: string }
  | { kind: 'not-drawn' }

/**
 * What a shot card shows, from the shot, its latest job, and whether its cast is approved. While a panel that
 * was drawn before is drawn again, or after that fails, its drawing stays on screen (previousUrl).
 */
export function panelPhase(shot: Shot, job: PanelJob | undefined, castReady: boolean, quality: 'draft' | 'final' = 'draft'): PanelPhase {
  const panel = shot.panel
  const previous = panel?.status === 'ready' && panel.image_url ? { previousUrl: panel.image_url } : {}
  if (job?.status === 'queued') {
    return job.position ? { kind: 'queued', position: job.position, estimateS: job.estimateS ?? 0, ...previous } : { kind: 'queued', ...previous }
  }
  if (job?.status === 'running' || (panel?.status === 'pending' && job?.status !== 'failed')) {
    return { kind: 'drawing', what: job?.kind === 'edit_panel' ? 'change' : quality, ...previous }
  }
  if (job?.status === 'failed') {
    const suggestion = panel?.suggested_change ? { suggestion: panel.suggested_change } : {}
    return { kind: 'failed', message: job.message ?? 'This panel could not be drawn.', ...previous, ...suggestion }
  }
  if (panel?.status === 'ready' && panel.image_url) {
    return { kind: 'ready', imageUrl: panel.image_url, revision: panel.shown_revision, outdated: panel.outdated }
  }
  if (panel?.status === 'failed') {
    return panel.suggested_change ? { kind: 'failed', message: REFUSED, suggestion: panel.suggested_change } : { kind: 'failed', message: 'This panel could not be drawn.' }
  }
  return castReady ? { kind: 'not-drawn' } : { kind: 'waiting-cast' }
}

/** A refused panel seen after its job's message was lost (a reload): the server's words for it. */
export const REFUSED = "Muse Image's safety filter turned this frame down twice. Redraw it and say plainly what happens, by look and action, or use the suggested change."

/**
 * After a Redraw: the drawing it replaced, while the user has not chosen between them. Null while the redraw
 * runs, when nothing was asked, or when that drawing is no longer among the panel's versions.
 */
export function redrawChoice(shot: Shot, from: number | undefined, job: PanelJob | undefined): { revision: number; imageUrl: string } | null {
  const panel = shot.panel
  if (from === undefined || !panel || panel.status !== 'ready' || inFlight(job?.status)) return null
  if (panel.shown_revision <= from) return null
  const previous = (panel.versions ?? []).find((v) => v.revision === from)
  return previous ? { revision: previous.revision, imageUrl: previous.image_url } : null
}

interface StoryboardActions {
  apply(event: ServerEvent): void
  load(project: Project): void
  /** The job status fallback answered for a job whose events were missed. */
  resolve(key: string, status: ResolvedStatus, message: string | null): void
  markRequested(shotId: string, requested: boolean): void
  jobStarted(shotId: string, job: PanelJob): void
  /** A Redraw was asked while revision `from` was shown; null: the choice is made (or the redraw failed). */
  redrawFrom(shotId: string, from: number | null): void
  set(patch: Partial<StoryboardState>): void
  setSync(sync: SyncStatus): void
  reset(): void
}

export const useStoryboardStore = create<StoryboardState & StoryboardActions>()((set) => ({
  ...initialStoryboard,
  apply: (event) =>
    set((s) => ({ ...reduceStoryboard(s, event), ...(event.type === 'job.updated' ? { lastJobAt: Date.now() } : {}) })),
  load: (project) => set((s) => loadProject(s, project)),
  resolve: (key, status, message) => set((s) => resolveJob(s, key, status, message)),
  markRequested: (shotId, requested) =>
    set((s) => ({ requested: requested ? { ...s.requested, [shotId]: true } : omit(s.requested, [shotId]) })),
  jobStarted: (shotId, job) => set((s) => ({ jobs: { ...s.jobs, [shotId]: job }, lastJobAt: Date.now() })),
  redrawFrom: (shotId, from) => set((s) => ({ redraws: from === null ? omit(s.redraws, [shotId]) : { ...s.redraws, [shotId]: from } })),
  set: (patch) => set(patch),
  setSync: (sync) => set({ sync }),
  reset: () => set(initialStoryboard),
}))
