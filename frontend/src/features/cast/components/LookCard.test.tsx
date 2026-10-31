import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LookCard, shotsLabel } from './LookCard'

const farmer = { id: 'farmer_costume', label: 'Farmer costume', clothes: 'blue denim overalls, red bandana', reference_url: '/media/farmer', from_shots: [2, 3, 4, 5, 6], sheet_error: null }

function card(over: Partial<Parameters<typeof LookCard>[0]> = {}) {
  const props = { look: farmer, name: 'Wren', imageSrc: '/media/farmer', clothes: farmer.clothes, redrawing: false, locked: false, onDescribe: vi.fn(), onRegenerate: vi.fn(), onRedrawWith: vi.fn(), ...over }
  render(<LookCard {...props} />)
  return props
}

describe('LookCard', () => {
  it('shows the look, the shots that wear it, and its sheet', () => {
    card()
    expect(screen.getByRole('group', { name: 'Wren: Farmer costume' })).toBeTruthy()
    expect(screen.getByText('Shots 2–6')).toBeTruthy()
    expect(screen.getByAltText('Reference sheet for Wren, farmer costume')).toBeTruthy()
  })

  it('edits the clothes and redraws, with Surprise me', () => {
    const props = card()
    fireEvent.change(screen.getByLabelText('What Wren wears: Farmer costume'), { target: { value: 'green overalls' } })
    expect(props.onDescribe).toHaveBeenCalledWith('green overalls')
    fireEvent.click(screen.getByRole('button', { name: 'Redraw Wren’s farmer costume' }))
    fireEvent.click(screen.getByRole('button', { name: 'Surprise me' }))
    expect(props.onRegenerate).toHaveBeenCalledWith({ change: '', surprise: true })
  })

  it('keeps the sheet on screen while it redraws', () => {
    card({ redrawing: true })
    expect(screen.getByAltText('Reference sheet for Wren, farmer costume')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toBe('Redrawing… about 20 s')
  })

  it('a sheet that failed says why, with Redraw and Edit description', () => {
    const props = card({ imageSrc: null, look: { ...farmer, reference_url: null, sheet_error: 'Muse Image is busy.' } })
    expect(screen.getByRole('alert').textContent).toContain('Muse Image is busy.')
    fireEvent.click(screen.getByRole('button', { name: 'Edit description' }))
    expect(document.activeElement).toBe(screen.getByLabelText('What Wren wears: Farmer costume'))
    fireEvent.click(screen.getByRole('button', { name: 'Redraw Wren’s farmer costume' }))
    fireEvent.click(screen.getByRole('button', { name: 'Redraw' }))
    expect(props.onRegenerate).toHaveBeenCalledWith({ change: '', surprise: false })
  })

  it('an edited description of a failed sheet draws with it', () => {
    const props = card({ imageSrc: null, clothes: 'green overalls', look: { ...farmer, reference_url: null, sheet_error: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Draw with this description' }))
    expect(props.onRedrawWith).toHaveBeenCalled()
  })

  it('after two refusals offers plain clothes to use instead of the same Redraw', () => {
    const onUseSuggestion = vi.fn()
    card({ imageSrc: null, onUseSuggestion, look: { ...farmer, reference_url: null, sheet_error: 'Turned down twice.', suggested_clothes: 'blue overalls, white shirt' } })
    expect(screen.getByTestId('sheet-suggestion').textContent).toContain('blue overalls, white shirt')
    fireEvent.click(screen.getByRole('button', { name: 'Use this description' }))
    expect(onUseSuggestion).toHaveBeenCalledWith('blue overalls, white shirt')
  })

  it('says it is drawing, and locks once the cast is approved', () => {
    card({ imageSrc: null, locked: true })
    expect(screen.getByText('Drawing Wren’s farmer costume… about 20 s')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Redraw/ })).toBeNull()
  })

  it('labels shot ranges', () => {
    expect(shotsLabel([])).toBe('')
    expect(shotsLabel([4])).toBe('Shot 4')
    expect(shotsLabel([2, 3, 4])).toBe('Shots 2–4')
    expect(shotsLabel([2, 5])).toBe('Shots 2, 5')
  })
})
