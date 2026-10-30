import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { emojiFlags } from '../../../test/flags'
import { GalleryGrid } from './GalleryGrid'

const base = { view: 'newest' as const, style: null, cards: [], error: null, reported: new Set<string>(), onView: vi.fn(), onStyle: vi.fn(), onHeart: vi.fn(), onReport: vi.fn() }

describe('GalleryGrid countries', () => {
  it('counts the countries stories come from and filters by one', async () => {
    const onCountry = vi.fn()
    const countries = [{ code: 'KE', entries: 2 }, { code: 'AE', entries: 1 }]
    const { rerender } = render(<GalleryGrid {...base} country={null} countries={countries} onCountry={onCountry} />)
    expect(screen.getByTestId('country-count').textContent).toBe('Stories from 2 countries')
    const filter = screen.getByLabelText<HTMLSelectElement>('Country')
    expect([...filter.options].map((o) => o.textContent)).toEqual(['Every country', '🇰🇪 Kenya (2)', '🇦🇪 United Arab Emirates (1)'])
    await userEvent.selectOptions(filter, 'KE')
    expect(onCountry).toHaveBeenLastCalledWith('KE')
    rerender(<GalleryGrid {...base} country="KE" countries={countries} onCountry={onCountry} />)
    await userEvent.selectOptions(screen.getByLabelText('Country'), '')
    expect(onCountry).toHaveBeenLastCalledWith(null)
  })

  it('says one country, and nothing at all before anyone signs with one', () => {
    const { rerender } = render(<GalleryGrid {...base} country={null} countries={[{ code: 'JP', entries: 4 }]} onCountry={vi.fn()} />)
    expect(screen.getByTestId('country-count').textContent).toBe('Stories from 1 country')
    rerender(<GalleryGrid {...base} country={null} countries={[]} onCountry={vi.fn()} />)
    expect(screen.queryByTestId('country-count')).toBeNull()
    expect(screen.queryByLabelText('Country')).toBeNull()
  })

  it('filters by country name alone where flags would show as letters', () => {
    emojiFlags(false)
    render(<GalleryGrid {...base} country={null} countries={[{ code: 'AE', entries: 1 }]} onCountry={vi.fn()} />)
    expect([...screen.getByLabelText<HTMLSelectElement>('Country').options].map((o) => o.textContent)).toEqual(['Every country', 'United Arab Emirates (1)'])
  })
})
