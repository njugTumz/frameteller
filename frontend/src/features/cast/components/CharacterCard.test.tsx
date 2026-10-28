import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { character } from '../../../test/builders'
import { CharacterCard } from './CharacterCard'

function card(over: Partial<Parameters<typeof CharacterCard>[0]> = {}) {
  const props = {
    character: character('ember', { name: 'Ember' }),
    imageSrc: null,
    description: 'ember, an original character',
    redrawing: false,
    locked: true,
    others: [character('pip', { name: 'Pip' }), character('ada', { name: 'Ada' })],
    onDescribe: vi.fn(),
    onRegenerate: vi.fn(),
    onRename: vi.fn(),
    onRemove: vi.fn(),
    onMerge: vi.fn(),
    ...over,
  }
  render(<CharacterCard {...props} />)
  return props
}

describe('CharacterCard cast management', () => {
  it('renames in place', async () => {
    const props = card()
    await userEvent.click(screen.getByRole('button', { name: 'Rename' }))
    const input = screen.getByLabelText('New name for Ember')
    await userEvent.clear(input)
    await userEvent.type(input, 'Spark{Enter}')
    expect(props.onRename).toHaveBeenCalledWith('Spark')
  })

  it('asks before removing, and says the shots keep their action', async () => {
    const props = card()
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    screen.getByText(/shots keep their action/)
    await userEvent.click(screen.getByRole('button', { name: 'Keep' }))
    expect(props.onRemove).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await userEvent.click(screen.getByRole('button', { name: 'Remove Ember' }))
    expect(props.onRemove).toHaveBeenCalledOnce()
  })

  it('merges into another character of the cast', async () => {
    const props = card()
    await userEvent.click(screen.getByRole('button', { name: 'Merge into…' }))
    expect((screen.getByRole('button', { name: 'Merge' }) as HTMLButtonElement).disabled).toBe(true)
    await userEvent.selectOptions(screen.getByLabelText('Ember is really…'), 'Pip')
    await userEvent.click(screen.getByRole('button', { name: 'Merge' }))
    expect(props.onMerge).toHaveBeenCalledWith('pip')
  })

  it('offers no merge when the character is alone', () => {
    card({ others: [] })
    expect(screen.queryByRole('button', { name: 'Merge into…' })).toBeNull()
  })
})
