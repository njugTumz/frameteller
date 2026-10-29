import { describe, expect, it } from 'vitest'
import { shot } from '../../test/builders'
import { byEpisode } from './episodes'

describe('byEpisode', () => {
  it('groups shots by episode and numbers them from 1 in each', () => {
    const groups = byEpisode([shot(1), shot(2), shot(3, { episode: 2 }), shot(4, { episode: 2 })])
    expect(groups.map((g) => [g.episode, g.shots.map((s) => s.number), g.numbered.map((s) => s.number)])).toEqual([
      [1, [1, 2], [1, 2]],
      [2, [3, 4], [1, 2]],
    ])
  })
})
