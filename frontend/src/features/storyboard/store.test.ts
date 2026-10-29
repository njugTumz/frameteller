import { describe, expect, it } from 'vitest'
import { panel, project, review, shot, supervisorEntry, turn } from '../../test/builders'
import { shotsToDraft } from './hooks/useAutoDraft'
import type { ServerEvent } from '../../shared/events'
import {
  DRAW_INTERRUPTED,
  EXPORT_INTERRUPTED,
  hasJobsInFlight,
  inFlightKeys,
  initialStoryboard,
  loadProject,
  panelPhase,
  REVIEW_WAIT_MS,
  reduceStoryboard,
  replaceShots,
  resolveJob,
  type StoryboardState,
} from './store'

const job = (status: 'queued' | 'running' | 'succeeded' | 'failed', over: object = {}) =>
  ({ type: 'job.updated', kind: 'generate_panel', key: 'k', status, shot_id: 's1', revision: 1, message: null, ...over }) as const

const withShots = (...shots: ReturnType<typeof shot>[]): StoryboardState => ({ ...initialStoryboard, shots, loaded: true })

describe('reduceStoryboard', () => {
  it('adds a card the moment shot.created arrives, in number order', () => {
    let s = reduceStoryboard(initialStoryboard, { type: 'shot.created', shot: shot(2) })
    s = reduceStoryboard(s, { type: 'shot.created', shot: shot(1) })
    expect(s.shots.map((x) => x.id)).toEqual(['s1', 's2'])
  })

  it('replaces corrected shots in place and renumbers the rest', () => {
    const s0 = withShots(shot(1), shot(2), shot(3))
    const s = reduceStoryboard(s0, {
      type: 'shots.replaced',
      turn: turn(2),
      removed_shot_ids: ['s2'],
      shots: [shot(2, { id: 'n2a' }), shot(3, { id: 'n2b' })],
    })
    expect(s.shots.map((x) => [x.id, x.number])).toEqual([['s1', 1], ['n2a', 2], ['n2b', 3], ['s3', 4]])
  })

  it('forgets jobs and requests of removed shots', () => {
    const s0 = { ...withShots(shot(1)), jobs: { s1: { kind: 'generate_panel' as const, status: 'failed' as const, revision: 1, message: 'x' } }, requested: { s1: true as const } }
    const s = reduceStoryboard(s0, { type: 'shots.replaced', turn: turn(1), removed_shot_ids: ['s1'], shots: [shot(1, { id: 'n1' })] })
    expect(s.jobs).toEqual({})
    expect(s.requested).toEqual({})
  })

  it('tracks panel jobs and marks the project stale when one finishes', () => {
    let s = reduceStoryboard(withShots(shot(1)), job('running'))
    expect(s.jobs.s1?.status).toBe('running')
    expect(s.stale).toBe(false)
    s = reduceStoryboard(s, job('succeeded'))
    expect(s.stale).toBe(true)
  })

  it('refreshes after pre-segmentation so masks are cached, without touching the panel job', () => {
    const s = reduceStoryboard(withShots(shot(1)), job('succeeded', { kind: 'pre_segment_panel' }))
    expect(s.stale).toBe(true)
    expect(s.jobs).toEqual({})
  })

  it.each<ServerEvent>([
    { type: 'session.started', mode: 'narrate' },
    { type: 'transcript.partial', text: 'x' },
    { type: 'turn.completed', turn: turn(1) },
    { type: 'cast.proposed', characters: [] },
    { type: 'error', message: 'x', fatal: false },
    { type: 'session.ended', turns: 1, shots: 1 },
  ])('ignores $type', (event) => {
    const s0 = withShots(shot(1))
    expect(reduceStoryboard(s0, event)).toBe(s0)
  })

  it('ignores cast jobs', () => {
    const s0 = withShots(shot(1))
    expect(reduceStoryboard(s0, job('running', { kind: 'generate_cast', shot_id: null }))).toBe(s0)
  })
})

describe('reveals, saved moves and exports', () => {
  it('replaces a revealed shot, marks its panel out of date and refetches the cast', () => {
    const before = withShots(shot(1, { panel: panel() }))
    const after = reduceStoryboard(before, { type: 'shot.updated', shot: shot(1, { character_ids: ['pip'], action: 'Pip hides in the reeds.' }) })
    expect(after.shots[0]).toMatchObject({ character_ids: ['pip'], action: 'Pip hides in the reeds.' })
    expect(after.shots[0]?.panel).toMatchObject({ outdated: true, image_url: panel().image_url })
    expect(after.stale).toBe(true)
    const phase = panelPhase(after.shots[0] as ReturnType<typeof shot>, undefined, true)
    expect(phase).toMatchObject({ kind: 'ready', outdated: true })
  })

  it('tracks compose jobs apart from panel jobs and refetches when one finishes', () => {
    let s = reduceStoryboard(withShots(shot(1, { panel: panel() })), job('running', { kind: 'compose_panel' }))
    expect(s.composing).toEqual({ s1: 'running' })
    expect(s.jobs).toEqual({})
    s = reduceStoryboard(s, job('succeeded', { kind: 'compose_panel' }))
    expect(s.stale).toBe(true)
    expect(loadProject(s, project({ shots: [shot(1, { panel: panel({ shown_revision: 2 }) })] })).composing).toEqual({})
  })

  it('follows the export progress and fetches the animatic when it is done', () => {
    const exportJob = (status: 'running' | 'succeeded', progress: number | null) =>
      ({ type: 'job.updated', kind: 'export_animatic', key: 'e', status, shot_id: null, revision: null, message: null, progress }) as const
    let s = reduceStoryboard(initialStoryboard, exportJob('running', 0.25))
    expect(s.exportJob).toEqual({ status: 'running', progress: 0.25, message: null, key: 'e', position: null, estimateS: null })
    s = reduceStoryboard(s, exportJob('succeeded', null))
    expect(s.exportJob?.progress).toBe(0.25)
    expect(s.stale).toBe(true)
    const animatic = { url: '/media/projects/p1/exports/a.mp4', duration_ms: 12000, subtitles: false, voiced: true }
    s = loadProject(s, project({ animatic, share_token: 'tok', narrations: [{ session: 't', duration_ms: 9000, url: '/media/x.wav' }] }))
    expect(s).toMatchObject({ animatic, shareToken: 'tok' })
    expect(s.narrations).toHaveLength(1)
  })

  it('shows the composite once there is one', () => {
    const p = panel({ revision: 1, shown_revision: 2, image_url: '/media/c.webp', base_image_url: '/media/r1.webp' })
    expect(panelPhase(shot(1, { panel: p }), undefined, true)).toMatchObject({ imageUrl: '/media/c.webp', revision: 2 })
  })
})

describe('loadProject', () => {
  it('takes panels from the server and drops jobs the server has caught up with', () => {
    const s0 = { ...withShots(shot(1)), jobs: { s1: { kind: 'generate_panel' as const, status: 'succeeded' as const, revision: 1, message: null } }, stale: true }
    const s = loadProject(s0, project({ shots: [shot(1, { panel: panel() })] }))
    expect(s.shots[0]?.panel?.image_url).toContain('/media/')
    expect(s.jobs).toEqual({})
    expect(s.stale).toBe(false)
    expect(s.sync).toBe('ready')
  })
})

describe('replaceShots', () => {
  it('appends when none of the removed shots are present', () => {
    expect(replaceShots([shot(1)], ['zz'], [shot(2, { id: 'n' })]).map((s) => s.id)).toEqual(['s1', 'n'])
  })
})

describe('panelPhase', () => {
  it('waits for the cast before anything is drawn, and says so', () => {
    expect(panelPhase(shot(1), undefined, false)).toEqual({ kind: 'waiting-cast' })
    expect(panelPhase(shot(1), undefined, true)).toEqual({ kind: 'not-drawn' })
  })

  it('shows drawing while a job runs or the panel is pending, then the image', () => {
    expect(panelPhase(shot(1), { kind: 'generate_panel', status: 'running', revision: 1, message: null }, true)).toEqual({ kind: 'drawing', what: 'draft' })
    expect(panelPhase(shot(1, { panel: panel({ status: 'pending', image_url: null }) }), undefined, true).kind).toBe('drawing')
    expect(panelPhase(shot(1, { panel: panel() }), undefined, true)).toEqual({ kind: 'ready', imageUrl: '/media/projects/p1/panels/s1/r1/image', revision: 1, outdated: false })
  })

  it('says an edit is a change', () => {
    expect(panelPhase(shot(1, { panel: panel() }), { kind: 'edit_panel', status: 'running', revision: 2, message: null }, true)).toEqual({ kind: 'drawing', what: 'change' })
  })

  it('shows the failure message', () => {
    expect(panelPhase(shot(1), { kind: 'generate_panel', status: 'failed', revision: 1, message: 'Out of credits.' }, true)).toEqual({ kind: 'failed', message: 'Out of credits.' })
  })
})

describe('shotsToDraft (cast approval gating)', () => {
  const shots = [shot(1), shot(2, { character_ids: ['owl'] }), shot(3, { panel: panel() })]

  it('drafts nothing while the cast is not approved', () => {
    expect(shotsToDraft(shots, {}, {}, () => false)).toEqual([])
  })

  it('drafts undrawn shots whose cast is approved, once', () => {
    const canDraw = (s: ReturnType<typeof shot>) => s.character_ids.every((c) => c === 'mira')
    expect(shotsToDraft(shots, {}, {}, canDraw).map((s) => s.id)).toEqual(['s1'])
    expect(shotsToDraft(shots, {}, { s1: true }, canDraw)).toEqual([])
    expect(shotsToDraft(shots, { s1: {} }, {}, canDraw)).toEqual([])
  })
})

describe('missed job updates (a dropped socket, a new studio version)', () => {
  const animatic = { url: '/media/projects/p1/exports/new.mp4', duration_ms: 12000, subtitles: false, voiced: true }
  const exporting = (from: string | null): StoryboardState => ({
    ...initialStoryboard,
    exportJob: { status: 'running', progress: 0.5, message: null, key: 'export_animatic:p1:abc', from },
  })

  it('sees a finished export in the fetched project', () => {
    expect(loadProject(exporting(null), project({ animatic })).exportJob).toMatchObject({ status: 'succeeded', progress: 1 })
    expect(loadProject(exporting('/media/old.mp4'), project({ animatic })).exportJob?.status).toBe('succeeded')
    // The same animatic as before: still waiting.
    expect(loadProject(exporting(animatic.url), project({ animatic })).exportJob?.status).toBe('running')
  })

  it('knows what it is waiting for, and which jobs it can ask about', () => {
    expect(hasJobsInFlight(initialStoryboard)).toBe(false)
    const s = reduceStoryboard(exporting(null), {
      type: 'job.updated', kind: 'compose_panel', key: 'compose_panel:p1:s1:r1:x', status: 'running', shot_id: 's1', revision: null, message: null,
    })
    expect(hasJobsInFlight(s)).toBe(true)
    expect(inFlightKeys(s).sort()).toEqual(['compose_panel:p1:s1:r1:x', 'export_animatic:p1:abc'])
  })

  it('settles jobs by their status, and says when one stopped with the old server', () => {
    const key = 'export_animatic:p1:abc'
    expect(resolveJob(exporting(null), key, 'running', null).exportJob?.status).toBe('running')
    expect(resolveJob(exporting(null), key, 'succeeded', null)).toMatchObject({ exportJob: { status: 'succeeded' }, stale: true })
    expect(resolveJob(exporting(null), key, 'unknown', null).exportJob).toMatchObject({ status: 'failed', message: EXPORT_INTERRUPTED })
    expect(resolveJob(exporting(null), key, 'failed', 'Too long.').exportJob?.message).toBe('Too long.')

    const drawing: StoryboardState = {
      ...initialStoryboard,
      jobs: { s1: { kind: 'generate_panel', status: 'running', revision: 2, message: null, key: 'generate_panel:p1:s1:r2' } },
      composing: { s2: 'running' },
      composingKeys: { s2: 'compose_panel:p1:s2:r1:y' },
    }
    expect(resolveJob(drawing, 'generate_panel:p1:s1:r2', 'unknown', null).jobs.s1).toMatchObject({ status: 'failed', message: DRAW_INTERRUPTED })
    expect(resolveJob(drawing, 'compose_panel:p1:s2:r1:y', 'unknown', null).composing).toEqual({})
    expect(resolveJob(drawing, 'nope', 'unknown', null)).toBe(drawing)
  })
})

describe('the continuity supervisor', () => {
  const entry = supervisorEntry({ shot_id: 's1' })

  it('adds each decision to the feed once and fetches the project for the badge', () => {
    const s0 = withShots(shot(1, { panel: panel() }))
    const event = { type: 'supervisor.fixed', entry, revision: 2, fixes: 1 } as const
    const s1 = reduceStoryboard(s0, event)
    expect(s1.supervisor).toEqual([entry])
    expect(s1.stale).toBe(true)
    expect(reduceStoryboard(s1, event).supervisor).toEqual([entry])
  })

  it('keeps polling for a while after a render until its review arrives', () => {
    const s0 = withShots(shot(1))
    const s1 = reduceStoryboard(s0, job('succeeded'), 1000)
    expect(s1.awaitingReview).toEqual({ s1: 1000 })
    expect(hasJobsInFlight(s1, 2000)).toBe(true)
    expect(hasJobsInFlight(s1, 1000 + REVIEW_WAIT_MS)).toBe(false) // gives up: the review may never come
    const s2 = reduceStoryboard(s1, { type: 'supervisor.reviewed', entry, revision: 1 })
    expect(s2.awaitingReview).toEqual({})
  })

  it('a loaded project with the review stops the wait, and a render seen only by polling starts it', () => {
    const waiting = { ...withShots(shot(1)), jobs: { s1: { kind: 'generate_panel' as const, status: 'queued' as const, revision: 1, message: null } } }
    const unreviewed = loadProject(waiting, project({ shots: [shot(1, { panel: panel() })] }), 5000)
    expect(unreviewed.awaitingReview).toEqual({ s1: 5000 })
    const reviewed = loadProject(unreviewed, project({ shots: [shot(1, { panel: panel({ review: review() }) })], supervisor: [entry] }), 6000)
    expect(reviewed.awaitingReview).toEqual({})
    expect(reviewed.supervisor).toEqual([entry])
  })

  it('does not wait for reviews when checks are off', () => {
    const off = loadProject(withShots(shot(1)), project({ continuity_checks: false }))
    expect(off.continuityChecks).toBe(false)
    expect(reduceStoryboard(off, job('succeeded')).awaitingReview).toEqual({})
  })
})

describe('busy studio and failed sheets', () => {
  it('a queued panel learns its place in line', () => {
    const s = { ...initialStoryboard, shots: [shot(1)] }
    const after = reduceStoryboard(s, { type: 'job.updated', kind: 'generate_panel', key: 'k', status: 'queued', shot_id: 's1', revision: 1, message: null, position: 3, estimate_s: 50 })
    expect(panelPhase(after.shots[0] as ReturnType<typeof shot>, after.jobs.s1, true)).toEqual({ kind: 'queued', position: 3, estimateS: 50 })
  })

  it('a failed cast job fetches the project again, so the card can say why', () => {
    const after = reduceStoryboard(initialStoryboard, { type: 'job.updated', kind: 'generate_cast', key: 'k', status: 'failed', shot_id: null, revision: null, message: "Amara's sheet couldn't be drawn." })
    expect(after.stale).toBe(true)
  })
})
