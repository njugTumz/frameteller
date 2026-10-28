import { describe, expect, it } from 'vitest'
import { panel, project, shot, turn } from '../../test/builders'
import { shotsToDraft } from './hooks/useAutoDraft'
import type { ServerEvent } from '../../shared/events'
import { initialStoryboard, loadProject, panelPhase, reduceStoryboard, replaceShots, type StoryboardState } from './store'

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
    expect(panelPhase(shot(1, { panel: panel() }), undefined, true)).toEqual({ kind: 'ready', imageUrl: '/media/projects/p1/panels/s1/r1/image', revision: 1 })
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
