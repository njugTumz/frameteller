import type { Wake } from '../api/health'
import { Button } from './Button'
import { Notice } from './Notice'

/** "Waking the studio…": the staging backend sleeps when nobody uses it. */
export function WakeNotice({ wake, onRetry }: { wake: Wake; onRetry: () => void }) {
  if (wake === 'ready' || wake === 'checking') return null
  if (wake === 'waking')
    return (
      <Notice title="Waking the studio…">
        It sleeps when nobody is using it, so the first visit takes up to 20 seconds. You can fill in the form meanwhile.
      </Notice>
    )
  return (
    <Notice tone="error" title="The studio did not wake up." action={<Button onClick={onRetry}>Try again</Button>}>
      Check your connection. If you are offline, reconnect, then try again.
    </Notice>
  )
}
