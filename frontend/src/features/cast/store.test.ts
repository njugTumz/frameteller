import { describe, expect, it } from 'vitest'
import type { ServerEvent } from '../../shared/events'
import { character, project, shot, turn } from '../../test/builders'
import { approvalBlock, castReadyFor, initialCast, loadCast, nameFromId, reduceCast, type CastState } from './store'

const castJob = (status: 'queued' | 'running' | 'succeeded' | 'failed', message: string | null = null): ServerEvent => ({
  type: 'job.updated',
  kind: 'generate_cast',
  key: 'cast-1',
  status,
  shot_id: null,
  revision: null,
  message,
})

describe('reduceCast', () => {
  it('expects a sheet for each new character a shot uses', () => {
    const s = reduceCast(initialCast, { type: 'shot.created', shot: shot(1, { character_ids: ['mira', 'grey_cat'] }) })
    expect(s.expected).toEqual(['mira', 'grey_cat'])
    expect(s.status).toBe('draft')
  })

  it('does the same for shots from a correction', () => {
    const s = reduceCast(initialCast, { type: 'shots.replaced', turn: turn(1), removed_shot_ids: [], shots: [shot(1, { character_ids: ['owl'] })] })
    expect(s.expected).toEqual(['owl'])
  })

  it('shows proposed sheets and needs a fresh approval', () => {
    const approved: CastState = { ...initialCast, status: 'approved', characters: [character('mira')], expected: ['owl'], redrawing: { mira: true } }
    const s = reduceCast(approved, { type: 'cast.proposed', characters: [character('mira', { description: 'new' }), character('owl')] })
    expect(s.status).toBe('draft')
    expect(s.characters.map((c) => [c.id, c.description])).toEqual([['mira', 'new'], ['owl', 'owl, an original character']])
    expect(s.expected).toEqual([])
    expect(s.redrawing).toEqual({})
  })

  it('follows reference-sheet jobs and reports a failure', () => {
    let s = reduceCast(initialCast, castJob('running'))
    expect(s.drawing).toBe(true)
    s = reduceCast(s, castJob('failed', 'The image model is busy.'))
    expect(s.drawing).toBe(false)
    expect(s.error).toBe('The image model is busy.')
    expect(reduceCast(s, castJob('succeeded')).drawing).toBe(false)
  })

  it.each<ServerEvent>([
    { type: 'session.started', mode: 'narrate' },
    { type: 'transcript.partial', text: 'x' },
    { type: 'turn.completed', turn: turn(1) },
    { type: 'error', message: 'x', fatal: false },
    { type: 'session.ended', turns: 1, shots: 1 },
    { type: 'job.updated', kind: 'generate_panel', key: 'k', status: 'running', shot_id: 's1', revision: 1, message: null },
  ])('ignores $type', (event) => {
    expect(reduceCast(initialCast, event)).toBe(initialCast)
  })

  it('does not change for a shot whose cast is known', () => {
    const s0 = { ...initialCast, status: 'approved' as const, characters: [character('mira')] }
    expect(reduceCast(s0, { type: 'shot.created', shot: shot(2) })).toBe(s0)
  })
})

describe('approval gating', () => {
  const ready: CastState = { ...initialCast, characters: [character('mira'), character('grey_cat')] }

  it('blocks approval until every sheet is drawn', () => {
    expect(approvalBlock(initialCast)).toBe('no-cast')
    expect(approvalBlock({ ...ready, drawing: true })).toBe('drawing')
    expect(approvalBlock({ ...ready, expected: ['owl'] })).toBe('drawing')
    expect(approvalBlock({ ...ready, characters: [character('mira', { reference_url: null })] })).toBe('missing-sheet')
    expect(approvalBlock(ready)).toBeNull()
  })

  it('lets a panel be drawn only once its whole cast is approved', () => {
    const both = shot(1, { character_ids: ['mira', 'grey_cat'] })
    expect(castReadyFor(ready, both)).toBe(false)
    const approved = { ...ready, status: 'approved' as const }
    expect(castReadyFor(approved, both)).toBe(true)
    expect(castReadyFor(approved, shot(2, { character_ids: ['owl'] }))).toBe(false)
    expect(castReadyFor({ ...approved, redrawing: { mira: true } }, both)).toBe(false)
    expect(castReadyFor(approved, shot(3, { character_ids: [] }))).toBe(true)
  })

  it('loads the cast and the characters still missing a sheet', () => {
    const s = loadCast(initialCast, { status: 'approved', characters: [character('mira')] }, [shot(1, { character_ids: ['mira', 'owl'] })])
    expect(s.status).toBe('approved')
    expect(s.expected).toEqual(['owl'])
    expect(loadCast(initialCast, project().cast, []).status).toBe('draft')
  })

  it('names characters whose sheets have not arrived', () => {
    expect(nameFromId('grey_cat')).toBe('Grey cat')
  })
})
