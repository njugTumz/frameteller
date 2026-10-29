import { describe, expect, it } from 'vitest'
import { parseRoute } from './router'

describe('parseRoute', () => {
  it.each([
    ['/', { name: 'start' }],
    ['/projects/p1', { name: 'studio', projectId: 'p1' }],
    ['/s/0123abcd', { name: 'share', token: '0123abcd' }],
    ['/privacy', { name: 'privacy' }],
    ['/gallery', { name: 'gallery' }],
    ['/admin', { name: 'admin' }],
    ['/judge', { name: 'judge' }],
    ['/s/../x', { name: 'missing' }],
    ['/elsewhere', { name: 'missing' }],
  ])('%s', (path, route) => {
    expect(parseRoute(path)).toEqual(route)
  })
})
