import type { Review } from '../../../shared/api/types'
import { Button } from '../../../shared/ui/Button'
import { modelName, seriousIssues } from '../model'

/** Under a flagged panel or sheet: what the supervisor saw, and what the user can do about it. */
export function NeedsYourEye({
  review,
  busy,
  onApply,
  onAccept,
  onRedraw,
  applyLabel = 'Apply suggested fix',
}: {
  review: Review
  busy: boolean
  onApply: () => void
  onAccept: () => void
  onRedraw?: () => void
  applyLabel?: string
}) {
  const issues = seriousIssues(review)
  return (
    <div role="group" aria-label="Continuity check" data-testid="needs-your-eye" className="flex flex-col gap-2 rounded-md border-2 border-ink bg-marker/25 p-3 text-sm">
      <p className="m-0 font-bold">The supervisor wants your eye on this</p>
      <ul className="m-0 flex list-none flex-col gap-1 p-0">
        {issues.map((i) => (
          <li key={`${i.rule_id}-${i.description}`}>
            <span className="font-mono text-xs text-muted">{i.rule_id}</span> {i.description}
          </li>
        ))}
      </ul>
      {review.fix_instruction && <p className="m-0 text-muted">Suggested fix: {review.fix_instruction}</p>}
      <div className="flex flex-wrap gap-2">
        {review.fix_instruction && (
          <Button size="sm" variant="ink" disabled={busy} onClick={onApply}>
            {applyLabel}
          </Button>
        )}
        <Button size="sm" disabled={busy} onClick={onAccept}>
          Accept anyway
        </Button>
        {onRedraw && (
          <Button size="sm" variant="quiet" disabled={busy} onClick={onRedraw}>
            Redraw
          </Button>
        )}
      </div>
      <p className="m-0 text-xs text-muted">Checked by {modelName(review.model)}</p>
    </div>
  )
}
