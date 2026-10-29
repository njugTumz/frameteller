import { act, fireEvent, render, renderHook, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { useFirstVisit } from '../hooks/useFirstVisit'
import { FirstVisitGuide } from './FirstVisitGuide'

afterEach(() => window.localStorage.clear())

describe('the first-visit guide', () => {
  it('shows three steps once, until dismissed', () => {
    const first = renderHook(() => useFirstVisit())
    expect(first.result.current.show).toBe(true)
    render(<FirstVisitGuide onDismiss={first.result.current.dismiss} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    act(() => fireEvent.click(screen.getByRole('button', { name: 'Got it' })))
    expect(first.result.current.show).toBe(false)
    expect(renderHook(() => useFirstVisit()).result.current.show).toBe(false)
  })
})
