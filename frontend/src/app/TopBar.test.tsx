import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { navigate } from './router'
import { TopBar } from './TopBar'

function bar() {
  const tour = vi.fn()
  render(
    <TopBar
      badge={<span data-testid="judge-badge">Judge access</span>}
      actions={[
        { label: 'Take the tour', onSelect: tour },
        { label: 'Gallery', href: '/gallery' },
      ]}
      menuOnly={[{ label: 'Privacy', href: '/privacy' }]}
      theme={(place) => <span>theme in the {place}</span>}
    />,
  )
  const menu = screen.getByRole('button', { name: 'Menu' })
  const panel = document.getElementById(menu.getAttribute('aria-controls') ?? '') as HTMLElement
  return { tour, menu, panel }
}

describe('TopBar on a phone (the ☰ menu)', () => {
  it('opens with aria-expanded, puts focus on the first item, and holds the actions, Privacy and the theme', () => {
    const { menu, panel } = bar()
    expect(menu.getAttribute('aria-expanded')).toBe('false')
    expect(panel.hidden).toBe(true)
    fireEvent.click(menu)
    expect(menu.getAttribute('aria-expanded')).toBe('true')
    expect(panel.hidden).toBe(false)
    expect(document.activeElement?.textContent).toBe('Take the tour')
    expect(Array.from(panel.querySelectorAll('a, button')).map((e) => e.textContent)).toEqual(['Take the tour', 'Gallery', 'Privacy'])
    expect(panel.textContent).toContain('theme in the menu')
    expect(screen.getByTestId('judge-badge')).toBeTruthy() // stays in the bar
  })

  it('Esc closes it and focus returns to ☰', () => {
    const { menu, panel } = bar()
    fireEvent.click(menu)
    fireEvent.keyDown(document.activeElement as Element, { key: 'Escape' })
    expect(panel.hidden).toBe(true)
    expect(document.activeElement).toBe(menu)
  })

  it('an outside tap, a chosen item or a navigation closes it', () => {
    const { tour, menu, panel } = bar()
    fireEvent.click(menu)
    fireEvent.pointerDown(document.body)
    expect(panel.hidden).toBe(true)

    fireEvent.click(menu)
    fireEvent.click(panel.querySelector('button') as HTMLElement)
    expect(tour).toHaveBeenCalledTimes(1)
    expect(panel.hidden).toBe(true)

    fireEvent.click(menu)
    act(() => navigate('/gallery'))
    expect(panel.hidden).toBe(true)
    act(() => navigate('/'))
  })
})
