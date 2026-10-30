import { describe, expect, it, vi } from 'vitest'
import { emojiFlags } from '../test/flags'
import { byName, byline, country, countryName, detectFlagEmoji, flag, resetFlagSupport } from './creator'

describe('creator byline', () => {
  it('shows the name and the country with its flag', () => {
    expect(byline({ name: 'Ama', country: 'KE' })).toBe('by Ama · 🇰🇪 Kenya')
  })

  it('falls back to an anonymous storyteller when both are empty', () => {
    expect(byline({ name: '', country: '' })).toBe('by an anonymous storyteller')
    expect(byline(null)).toBe('by an anonymous storyteller')
    expect(byline({ name: '   ', country: '' })).toBe('by an anonymous storyteller')
  })

  it('shows whichever one was given', () => {
    expect(byline({ name: 'Captain Biscuit', country: '' })).toBe('by Captain Biscuit')
    expect(byline({ name: '', country: 'AE' })).toBe('by a storyteller from 🇦🇪 United Arab Emirates')
  })
})

describe('countries', () => {
  it('makes flags from ISO codes, and nothing from anything else', () => {
    expect(flag('JP')).toBe('🇯🇵')
    expect(flag('jp')).toBe('')
    expect(flag('')).toBe('')
    expect(country('GB')).toBe('🇬🇧 United Kingdom')
  })

  it('names countries in English', () => {
    expect(countryName('KE')).toBe('Kenya')
    expect(countryName('CI')).toBe('Côte d’Ivoire')
  })

  it('sorts the dropdown by name, with the flag and the code', () => {
    const list = byName(['ZA', 'AE', 'KE'])
    expect(list.map((c) => c.code)).toEqual(['KE', 'ZA', 'AE'])
    expect(list[0]?.label).toBe('🇰🇪 Kenya (KE)')
  })
})

describe('where flag emoji draw as letters (Windows)', () => {
  it('detects colour flags, and letters or no canvas as no flags', () => {
    emojiFlags(true)
    expect(detectFlagEmoji()).toBe(true)
    emojiFlags(false)
    expect(detectFlagEmoji()).toBe(false)
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    expect(detectFlagEmoji()).toBe(false)
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(detectFlagEmoji()).toBe(false)
  })

  it('shows only the country name, without the two-letter code', () => {
    emojiFlags(false)
    expect(byline({ name: 'Ama', country: 'AE' })).toBe('by Ama · United Arab Emirates')
    expect(byline({ name: '', country: 'KE' })).toBe('by a storyteller from Kenya')
    expect(country('JP')).toBe('Japan')
  })

  it('keeps the ISO code in the dropdown, without a flag', () => {
    emojiFlags(false)
    expect(byName(['KE', 'AE']).map((c) => c.label)).toEqual(['Kenya (KE)', 'United Arab Emirates (AE)'])
  })

  it('checks the canvas once, until reset', () => {
    emojiFlags(false)
    const spy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext')
    country('KE')
    country('AE')
    expect(spy).toHaveBeenCalledTimes(1)
    resetFlagSupport()
    country('KE')
    expect(spy).toHaveBeenCalledTimes(2)
  })
})
