import { describe, expect, it } from 'vitest'
import { inLine, ordinal } from './format'

describe('waiting in line (ADR 0016)', () => {
  it('says the place and a rounded-up estimate', () => {
    expect(inLine(1, 12)).toBe("You're next, about 20 s")
    expect(inLine(3, 130)).toBe("You're 3rd in line, about 3 min")
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal)).toEqual(['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd'])
  })
})
