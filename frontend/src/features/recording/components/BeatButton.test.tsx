import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { useBeatShortcut } from '../hooks/useBeatShortcut'
import { BeatButton } from './BeatButton'

function Harness({ enabled, onBeat }: { enabled: boolean; onBeat: () => void }) {
  useBeatShortcut(enabled, onBeat)
  return (
    <>
      <BeatButton enabled={enabled} beats={0} onBeat={onBeat} />
      <button type="button">Stop telling</button>
      <label>
        Fix
        <input />
      </label>
    </>
  )
}

describe('Next shot', () => {
  it('sends a beat when clicked, and says Space does the same', async () => {
    const onBeat = vi.fn()
    render(<Harness enabled onBeat={onBeat} />)
    const button = screen.getByRole('button', { name: /next shot/i })
    expect(button).toHaveProperty('ariaKeyShortcuts', 'Space')
    await userEvent.click(button)
    expect(onBeat).toHaveBeenCalledTimes(1)
  })

  it('sends a beat on Space, once per press, and does not press the focused button', async () => {
    const onBeat = vi.fn()
    const stop = vi.fn()
    render(<Harness enabled onBeat={onBeat} />)
    const other = screen.getByRole('button', { name: 'Stop telling' })
    other.addEventListener('click', stop)
    other.focus()
    await userEvent.keyboard('[Space]')
    expect(onBeat).toHaveBeenCalledTimes(1)
    expect(stop).not.toHaveBeenCalled()
    await userEvent.keyboard('[Space>3/]') // held down: repeats are ignored
    expect(onBeat).toHaveBeenCalledTimes(2)
  })

  it('leaves Space alone while typing', async () => {
    const onBeat = vi.fn()
    render(<Harness enabled onBeat={onBeat} />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Fix' }), 'a b')
    expect(onBeat).not.toHaveBeenCalled()
    expect(screen.getByRole('textbox', { name: 'Fix' })).toHaveProperty('value', 'a b')
  })

  it('is off when not telling', async () => {
    const onBeat = vi.fn()
    render(<Harness enabled={false} onBeat={onBeat} />)
    expect(screen.getByRole('button', { name: /next shot/i })).toHaveProperty('disabled', true)
    await userEvent.keyboard('[Space]')
    expect(onBeat).not.toHaveBeenCalled()
  })
})
