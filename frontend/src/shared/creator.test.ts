import { describe, expect, it } from 'vitest'
import { byName, byline, country, countryName, flag } from './creator'

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
