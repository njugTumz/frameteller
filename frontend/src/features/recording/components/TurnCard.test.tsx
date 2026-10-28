import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { turn } from '../../../test/builders'
import { replaceWord } from '../words'
import { TurnCard } from './TurnCard'

describe('transcript correction', () => {
  it('fixes one clicked word and sends the whole corrected turn', async () => {
    const onCorrect = vi.fn()
    render(
      <ol>
        <TurnCard turn={turn(1, 'Sinuan. Night, a rainy alley.')} index={0} status={undefined} onCorrect={onCorrect} />
      </ol>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Sinuan.' }))
    const field = screen.getByRole('textbox', { name: /fix “sinuan\.”/i })
    await userEvent.clear(field)
    await userEvent.type(field, 'Scene one.')
    await userEvent.click(screen.getByRole('button', { name: 'Fix this word' }))
    expect(onCorrect).toHaveBeenCalledWith('t-b1', 'Scene one. Night, a rainy alley.')
  })

  it('edits the whole line from the keyboard', async () => {
    const onCorrect = vi.fn()
    render(
      <ol>
        <TurnCard turn={turn(2, 'She hears a sound')} index={1} status={undefined} onCorrect={onCorrect} />
      </ol>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Fix words' }))
    const field = screen.getByRole('textbox', { name: /fix this line/i })
    await userEvent.clear(field)
    await userEvent.type(field, 'She hears a soft mew{Enter}')
    await userEvent.click(screen.getByRole('button', { name: 'Fix this line' }))
    expect(onCorrect).toHaveBeenCalledWith('t-b2', 'She hears a soft mew')
  })

  it('sends nothing when the text did not change, and shows progress while redirecting', async () => {
    const onCorrect = vi.fn()
    const { rerender } = render(
      <ol>
        <TurnCard turn={turn(1, 'A cat')} index={0} status={undefined} onCorrect={onCorrect} />
      </ol>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'cat' }))
    await userEvent.click(screen.getByRole('button', { name: 'Fix this word' }))
    expect(onCorrect).not.toHaveBeenCalled()
    rerender(
      <ol>
        <TurnCard turn={turn(1, 'A cat')} index={0} status="sending" onCorrect={onCorrect} />
      </ol>,
    )
    expect(screen.getByText('Redirecting this shot…')).toBeTruthy()
  })

  it('replaces or removes one word by position', () => {
    expect(replaceWord('the cat the hat', 2, 'a')).toBe('the cat a hat')
    expect(replaceWord('um the cat', 0, ' ')).toBe('the cat')
    expect(replaceWord('the cat', 9, 'x')).toBe('the cat')
  })
})
