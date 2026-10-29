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
    { type: 'session.started', mode: 'read' },
    { type: 'script.accepted', episodes: [{ number: 1, paragraphs: [{ narration: 'Lena waves.', direction: 'Wide shot. Lena waves.' }] }] },
    { type: 'teleprompter.advanced', paragraph: 1 },
    { type: 'script.voiced', paragraph: 0, episode: 1, text: 'Lena salue.', original: 'Lena waves.', audio_url: '/media/projects/p1/speech/a.wav', duration_ms: 1200 },
    { type: 'script.paused', next_paragraph: 3, next_episode: 2, reason: 'episode' },
    { type: 'script.resumed', next_paragraph: 3 },
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
    ['an unknown session mode', raw({ type: 'session.started', mode: 'sing' })],
    ['a pause without a reason', raw({ type: 'script.paused', next_paragraph: 1, next_episode: 1 })],
    ['a paragraph without its direction', raw({ type: 'script.accepted', episodes: [{ number: 1, paragraphs: [{ narration: 'x' }] }] })],
    ['a silence without its level', raw({ type: 'audio.silent', after_ms: 8000 })],
    ['a progress that is not a number', raw({ type: 'job.updated', kind: 'export_animatic', key: 'k', status: 'running', shot_id: null, revision: null, message: null, progress: 'half' })],
  ])('rejects %s', (_, text) => {
    expect(parseServerEvent(text)).toBeNull()
  })

  it('ignores binary frames', () => {
    expect(parseServerEvent(new ArrayBuffer(4))).toBeNull()
  })
})

describe('supervisor events', () => {
  const entry = {
    at: '2026-10-29T12:00:00+00:00',
    subject: 'Shot 4',
    outcome: 'needs_user',
    message: 'Shot 4 needs your eye: Pip is missing (CONT-01; an edit cannot fix this).',
    rule_ids: ['CONT-01'],
    model: 'muse-spark-1.3',
    shot_id: 's4',
    character_id: null,
  }

  it('parses the three supervisor events and refuses malformed ones', () => {
    const issues = [{ rule_id: 'CONT-01', severity: 'blocker', description: 'Pip is missing' }]
    expect(parseServerEvent(JSON.stringify({ type: 'supervisor.reviewed', entry, revision: 1 }))).not.toBeNull()
    expect(parseServerEvent(JSON.stringify({ type: 'supervisor.fixed', entry, revision: 2, fixes: 1 }))).not.toBeNull()
    expect(parseServerEvent(JSON.stringify({ type: 'supervisor.needs_user', entry, issues, fix_instruction: '', revision: 1 }))).not.toBeNull()
    expect(parseServerEvent(JSON.stringify({ type: 'supervisor.fixed', entry, revision: null, fixes: 1 }))).toBeNull()
    expect(parseServerEvent(JSON.stringify({ type: 'supervisor.reviewed', entry: { ...entry, outcome: 'great' }, revision: 1 }))).toBeNull()
  })
})
