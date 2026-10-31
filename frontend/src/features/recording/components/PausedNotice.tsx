import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'

export const PAUSED = 'Paused when the screen locked'

/** Telling stopped because the phone locked or the page was hidden. Nothing said before it is lost. */
export function PausedNotice({ reading, onDismiss }: { reading: boolean; onDismiss: () => void }) {
  return (
    <div data-testid="paused-notice">
      <Notice
        title={PAUSED}
        action={
          <Button size="sm" variant="quiet" onClick={onDismiss}>
            OK
          </Button>
        }
      >
        {reading
          ? 'Your shots are saved. Press Continue to hear the rest.'
          : 'Everything you said is saved as shots. Tell more when you’re ready, and keep the screen on while you tell.'}
      </Notice>
    </div>
  )
}
