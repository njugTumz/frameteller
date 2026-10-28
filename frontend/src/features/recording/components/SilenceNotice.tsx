import { useId } from 'react'
import type { AudioInput } from '../../../shared/audio/inputs'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'

/** audio.silent: eight seconds of near-silence and no words. Usually a muted or wrong microphone. */
export function SilenceNotice({
  micLabel,
  inputs,
  deviceId,
  onPick,
  onDismiss,
}: {
  micLabel: string
  inputs: AudioInput[]
  deviceId: string | null
  onPick: (deviceId: string) => void
  onDismiss: () => void
}) {
  const id = useId()
  const others = inputs.length > 1
  return (
    <div data-testid="silence-notice">
      <Notice
        tone="warn"
        title="We can’t hear you"
        action={
          <Button size="sm" variant="quiet" onClick={onDismiss}>
            Dismiss
          </Button>
        }
      >
        <p className="m-0">
          Recording from <strong className="text-ink">{micLabel || 'the default microphone'}</strong>, and it is almost silent. Check it is not muted
          {others ? ', or pick another microphone.' : '.'}
        </p>
        {others && (
          <div className="mt-2 flex flex-col gap-1">
            <label htmlFor={id} className="text-sm font-semibold text-ink">
              Microphone
            </label>
            <select
              id={id}
              value={deviceId ?? inputs.find((i) => i.label === micLabel)?.deviceId ?? ''}
              onChange={(e) => onPick(e.target.value)}
              className="rounded border-[1.5px] border-ink bg-paper px-2 py-1.5 text-sm"
            >
              {!deviceId && !inputs.some((i) => i.label === micLabel) && <option value="">{micLabel || 'Default microphone'}</option>}
              {inputs.map((input) => (
                <option key={input.deviceId} value={input.deviceId}>
                  {input.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </Notice>
    </div>
  )
}
