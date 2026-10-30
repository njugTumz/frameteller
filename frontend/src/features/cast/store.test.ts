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

describe('looks: a costume put on mid-story (ADR 0018)', () => {
  const farmer = { id: 'farmer_costume', label: 'Farmer costume', clothes: 'blue denim overalls, red bandana', reference_url: '/media/wren/looks/farmer', from_shots: [2, 3], sheet_error: null }
  const wren = character('wren', { looks: [farmer] })
  const wrenUndrawn = character('wren', { looks: [{ ...farmer, reference_url: null }] })
  const inCostume = shot(3, { character_ids: ['wren'], looks: { wren: 'farmer_costume' } })
  const approved: CastState = { ...initialCast, status: 'approved', characters: [character('wren')] }

  it('waits for the costume sheet when a shot wears a new look', () => {
    const next = reduceCast(approved, { type: 'shot.created', shot: inCostume })
    expect(next.expected).toEqual(['wren/farmer_costume'])
    expect(next.status).toBe('draft')
    expect(nameFromId('wren/farmer_costume')).toBe('Wren’s farmer costume')
    expect(approvalBlock(next)).toBe('drawing')
  })

  it('a shot updated into the costume waits too', () => {
    expect(reduceCast(approved, { type: 'shot.updated', shot: inCostume }).expected).toEqual(['wren/farmer_costume'])
  })

  it('the drawn costume arrives, clears what was waiting or being redrawn, and needs approval', () => {
    const waiting: CastState = { ...approved, status: 'draft', expected: ['wren/farmer_costume'], redrawing: { 'wren/farmer_costume': true }, edits: { 'wren/farmer_costume': 'x' } }
    const next = reduceCast(waiting, { type: 'cast.proposed', characters: [wren] })
    expect(next.expected).toEqual([])
    expect(next.redrawing).toEqual({})
    expect(next.edits).toEqual({})
    expect(approvalBlock(next)).toBeNull()
  })

  it('a look without its sheet blocks approval', () => {
    expect(approvalBlock({ ...approved, status: 'draft', characters: [wrenUndrawn] })).toBe('missing-sheet')
  })

  it('a panel in the costume is drawn only once its sheet is here and approved', () => {
    expect(castReadyFor({ ...approved, characters: [wrenUndrawn] }, inCostume)).toBe(false)
    expect(castReadyFor({ ...approved, characters: [wren] }, inCostume)).toBe(true)
    expect(castReadyFor({ ...approved, characters: [wren], redrawing: { 'wren/farmer_costume': true } }, inCostume)).toBe(false)
    expect(castReadyFor({ ...approved, characters: [wrenUndrawn] }, shot(1, { character_ids: ['wren'] }))).toBe(true)
  })

  it('loading a project expects the looks its shots wear', () => {
    const p = project({ cast: { status: 'draft', characters: [wrenUndrawn] }, shots: [inCostume] })
    expect(loadCast(initialCast, p.cast, p.shots).expected).toEqual(['wren/farmer_costume'])
  })
})
