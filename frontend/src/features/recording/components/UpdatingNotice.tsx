import { Notice } from '../../../shared/ui/Notice'

export const UPDATING = 'Updating the studio, your work is safe'

/** The session socket dropped (usually a new version of the studio going live): shown until the project reloads. */
export function UpdatingNotice() {
  return (
    <Notice title={UPDATING} className="motion-safe:animate-pulse">
      Everything you made is saved. Drawings and exports carry on and show up here in a moment.
    </Notice>
  )
}
