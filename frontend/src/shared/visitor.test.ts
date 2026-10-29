import { afterEach, describe, expect, it, vi } from 'vitest'
import { visitorId } from './visitor'

describe('visitorId', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('is random, kept by this browser, and in the shape the backend accepts', () => {
    const id = visitorId()
    expect(id).toMatch(/^[A-Za-z0-9-]{8,64}$/)
    expect(visitorId()).toBe(id)
    window.localStorage.clear()
    expect(visitorId()).not.toBe(id)
  })

  it('still works when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })
    const id = visitorId()
    expect(id).toMatch(/^[A-Za-z0-9-]{8,64}$/)
    expect(visitorId()).toBe(id)
  })
})
