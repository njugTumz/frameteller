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

describe('CharacterCard when a sheet failed', () => {
  const failed = character('amara', { name: 'Amara', reference_url: null, sheet_error: "Muse Image's safety filter turned it down. Describe them by look and role (no ages), then try again." })

  it('names the character, says why, and offers Try again and Edit description', async () => {
    const props = card({ character: failed, locked: false, description: failed.description })
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('Amara’s sheet couldn’t be drawn.')
    expect(alert.textContent).toContain('safety filter')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(props.onRegenerate).toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Edit description' }))
    expect(document.activeElement).toBe(screen.getByLabelText('Description of Amara'))
  })

  it('draws with the edited description once it changed', async () => {
    const onRedrawWith = vi.fn()
    card({ character: failed, locked: false, description: 'a kite maker’s apprentice with an orange headscarf', onRedrawWith })
    await userEvent.click(screen.getByRole('button', { name: 'Draw with this description' }))
    expect(onRedrawWith).toHaveBeenCalled()
  })
})
