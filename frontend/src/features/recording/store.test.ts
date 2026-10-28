import { beforeEach, describe, expect, it } from 'vitest'
import { shot, turn } from '../../test/builders'
import { initialRecording, reduceRecording, useRecordingStore, type RecordingState } from './store'

const live: RecordingState = { ...initialRecording, telling: 'live' }

describe('reduceRecording', () => {
  it('goes live on session.started and clears an old problem', () => {
    const s = reduceRecording({ ...initialRecording, telling: 'connecting', problem: { kind: 'connection', message: 'x' } }, { type: 'session.started', mode: 'narrate' })
    expect(s.telling).toBe('live')
    expect(s.problem).toBeNull()
  })

  it('replaces the partial instead of appending', () => {
    const a = reduceRecording(live, { type: 'transcript.partial', text: 'Night' })
    const b = reduceRecording(a, { type: 'transcript.partial', text: 'Night. A rainy alley' })
    expect(b.partial).toBe('Night. A rainy alley')
  })

  it('adds completed turns in order and updates a repeated id in place', () => {
    let s = reduceRecording(live, { type: 'turn.completed', turn: turn(1) })
    s = reduceRecording(s, { type: 'turn.completed', turn: turn(2) })
    s = reduceRecording(s, { type: 'turn.completed', turn: turn(1, 'again') })
    expect(s.turns.map((t) => [t.id, t.text])).toEqual([['t-b1', 'again'], ['t-b2', 'words of beat 2']])
  })

  it('applies a correction when shots.replaced arrives', () => {
    const s0 = { ...live, turns: [turn(1, 'Sinuan. Night')], correcting: { 't-b1': 'sending' as const } }
    const s = reduceRecording(s0, { type: 'shots.replaced', turn: turn(1, 'Scene one. Night'), removed_shot_ids: ['s1'], shots: [shot(1)] })
    expect(s.turns[0]?.text).toBe('Scene one. Night')
    expect(s.correcting).toEqual({})
  })

  it('keeps non-fatal errors as notices, without repeats', () => {
    let s = reduceRecording(live, { type: 'error', message: 'One turn could not be directed.', fatal: false })
    s = reduceRecording(s, { type: 'error', message: 'One turn could not be directed.', fatal: false })
    expect(s.notices).toEqual(['One turn could not be directed.'])
    expect(s.telling).toBe('live')
  })

  it('marks a pending correction failed when the server says it could not apply it', () => {
    const s = reduceRecording({ ...live, correcting: { 't-b1': 'sending' } }, { type: 'error', message: 'That correction could not be applied.', fatal: false })
    expect(s.correcting).toEqual({ 't-b1': 'failed' })
  })

  it('stops telling on a fatal error and says why', () => {
    const s = reduceRecording(live, { type: 'error', message: 'The transcriber stopped.', fatal: true })
    expect(s.telling).toBe('idle')
    expect(s.problem).toEqual({ kind: 'server', message: 'The transcriber stopped.' })
  })

  it('ends on session.ended and clears the partial', () => {
    const s = reduceRecording({ ...live, partial: 'last words' }, { type: 'session.ended', turns: 6, shots: 6 })
    expect(s.telling).toBe('ended')
    expect(s.partial).toBe('')
  })

  it.each(['shot.created', 'cast.proposed', 'job.updated'] as const)('ignores %s', (type) => {
    const event =
      type === 'shot.created'
        ? { type, shot: shot(1) }
        : type === 'cast.proposed'
          ? { type, characters: [] }
          : { type, kind: 'generate_panel' as const, key: 'k', status: 'queued' as const, shot_id: 's1', revision: 1, message: null }
    expect(reduceRecording(live, event)).toBe(live)
  })
})

describe('silence', () => {
  it('warns on audio.silent until words arrive', () => {
    let s = reduceRecording({ ...initialRecording, telling: 'live' }, { type: 'audio.silent', after_ms: 8000, level: 0.002 })
    expect(s.silent).toBe(true)
    s = reduceRecording(s, { type: 'transcript.partial', text: '' })
    expect(s.silent).toBe(true)
    s = reduceRecording(s, { type: 'transcript.partial', text: 'Scene one' })
    expect(s.silent).toBe(false)
  })

  it('says nothing was heard when the session ends without words', () => {
    const s = reduceRecording({ ...initialRecording, telling: 'finishing', silent: true }, { type: 'session.ended', turns: 0, shots: 0, heard: false })
    expect(s).toMatchObject({ telling: 'ended', heardNothing: true, silent: false })
    expect(reduceRecording(s, { type: 'session.started', mode: 'narrate' }).heardNothing).toBe(false)
    expect(reduceRecording(initialRecording, { type: 'session.ended', turns: 1, shots: 1, heard: true }).heardNothing).toBe(false)
  })
})

describe('useRecordingStore', () => {
  beforeEach(() => useRecordingStore.getState().reset())

  it('counts beats and tracks corrections', () => {
    const s = useRecordingStore.getState()
    s.beatSent()
    s.beatSent()
    s.correctionSent('t-b1')
    expect(useRecordingStore.getState().beats).toBe(2)
    expect(useRecordingStore.getState().correcting).toEqual({ 't-b1': 'sending' })
  })
})
