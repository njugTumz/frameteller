import { renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useNoindex } from './useNoindex'

const robots = () => document.head.querySelectorAll('meta[name="robots"]')

describe('useNoindex', () => {
  afterEach(() => robots().forEach((m) => m.remove()))

  it('adds a noindex tag while active and removes it after', () => {
    const { rerender, unmount } = renderHook(({ on }) => useNoindex(on), { initialProps: { on: true } })
    expect(robots()[0]?.getAttribute('content')).toBe('noindex, nofollow')
    rerender({ on: false })
    expect(robots()).toHaveLength(0)
    rerender({ on: true })
    unmount()
    expect(robots()).toHaveLength(0)
  })

  it('never relaxes a noindex the build put in the page', () => {
    const fixed = Object.assign(document.createElement('meta'), { name: 'robots', content: 'noindex, nofollow' })
    document.head.append(fixed)
    const { unmount } = renderHook(() => useNoindex(false))
    unmount()
    expect(robots()).toHaveLength(1)
  })
})
