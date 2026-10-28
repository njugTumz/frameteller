import { describe, expect, it } from 'vitest'
import { shot, turn } from '../test/builders'
import { parseServerEvent } from './events'

const raw = (v: unknown) => JSON.stringify(v)

describe('parseServerEvent', () => {
  it.each([
    { type: 'session.started', mode: 'narrate' },
    { type: 'transcript.partial', text: 'Night. A rainy alley' },
    { type: 'turn.completed', turn: turn(1) },
    { type: 'shot.created', shot: shot(1) },
    { type: 'shots.replaced', turn: turn(1), removed_shot_ids: ['s1'], shots: [shot(1)] },
    { type: 'cast.proposed', characters: [{ id: 'mira', name: 'Mira', description: 'a girl', reference_url: null }] },
    { type: 'job.updated', kind: 'generate_panel', key: 'k', status: 'running', shot_id: 's1', revision: 1, message: null },
    { type: 'error', message: 'Could not direct that turn.', fatal: false },
    { type: 'session.ended', turns: 6, shots: 6 },
    { type: 'session.ended', turns: 0, shots: 0, heard: false },
    { type: 'shot.updated', shot: shot(2) },
    { type: 'audio.silent', after_ms: 8000, level: 0.003 },
    { type: 'job.updated', kind: 'export_animatic', key: 'k', status: 'running', shot_id: null, revision: null, message: null, progress: 0.4 },
    { type: 'job.updated', kind: 'compose_panel', key: 'k', status: 'queued', shot_id: 's1', revision: 1, message: null, progress: null },
  ])('accepts $type', (event) => {
    expect(parseServerEvent(raw(event))).toEqual(event)
  })

  it.each([
    ['not JSON', '{oops'],
    ['an array', raw([1])],
    ['an unknown type', raw({ type: 'speaker', label: 'A' })],
    ['a missing field', raw({ type: 'turn.completed', turn: { id: 't1' } })],
    ['a wrong job status', raw({ type: 'job.updated', kind: 'generate_panel', key: 'k', status: 'done', shot_id: null, revision: null, message: null })],
    ['an error without fatal', raw({ type: 'error', message: 'x' })],
    ['a silence without its level', raw({ type: 'audio.silent', after_ms: 8000 })],
    ['a progress that is not a number', raw({ type: 'job.updated', kind: 'export_animatic', key: 'k', status: 'running', shot_id: null, revision: null, message: null, progress: 'half' })],
  ])('rejects %s', (_, text) => {
    expect(parseServerEvent(text)).toBeNull()
  })

  it('ignores binary frames', () => {
    expect(parseServerEvent(new ArrayBuffer(4))).toBeNull()
  })
})
