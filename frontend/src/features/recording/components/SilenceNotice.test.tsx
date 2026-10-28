import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HEARD_NOTHING, TellingControls } from './TellingControls'
import { SilenceNotice } from './SilenceNotice'

describe('We can’t hear you', () => {
  it('names the microphone and switches to another one', async () => {
    const onPick = vi.fn()
    render(
      <SilenceNotice
        micLabel="Built-in microphone"
        inputs={[
          { deviceId: 'a', label: 'Built-in microphone' },
          { deviceId: 'b', label: 'USB headset' },
        ]}
        deviceId={null}
        onPick={onPick}
        onDismiss={vi.fn()}
      />,
    )
    screen.getByText('We can’t hear you')
    screen.getByText('Built-in microphone', { selector: 'strong' })
    await userEvent.selectOptions(screen.getByLabelText('Microphone'), 'USB headset')
    expect(onPick).toHaveBeenCalledWith('b')
  })

  it('says nothing was heard instead of done', () => {
    const noop = vi.fn()
    const { rerender } = render(<TellingControls telling="ended" heardNothing level={0} beats={0} onStart={noop} onStop={noop} onBeat={noop} />)
    expect(screen.getByRole('status').textContent).toContain(HEARD_NOTHING)
    rerender(<TellingControls telling="ended" level={0} beats={0} onStart={noop} onStop={noop} onBeat={noop} />)
    expect(screen.getByRole('status').textContent).toContain('Done. Tell more any time.')
  })
})
