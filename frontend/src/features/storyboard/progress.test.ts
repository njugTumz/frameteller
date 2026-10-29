import { describe, expect, it } from 'vitest'
import type { Shot } from '../../shared/api/types'
import { boardProgress } from './progress'

const shot = (id: string, status: 'ready' | 'pending' | null): Shot => ({ id, panel: status ? { status } : null }) as unknown as Shot

describe('boardProgress', () => {
  it('counts the shots being drawn', () => {
    const shots = [shot('a', 'ready'), shot('b', 'ready'), shot('c', null), shot('d', null)]
    const running = { kind: 'generate_panel', status: 'running', revision: 1, message: null } as const
    expect(boardProgress(shots, { c: running }, {})).toBe('Drawing shot 3 of 4…')
    expect(boardProgress(shots, { c: running, d: { ...running, status: 'queued' } }, {})).toBe('Drawing shots 3–4 of 4…')
  })

  it('says when continuity is being checked, then when everything is drawn', () => {
    const shots = [shot('a', 'ready'), shot('b', 'ready')]
    expect(boardProgress(shots, {}, { b: 1 })).toBe('Checking continuity…')
    expect(boardProgress(shots, {}, {})).toBe('All 2 shots are drawn.')
    expect(boardProgress([], {}, {})).toBeNull()
  })
})
