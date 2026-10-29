import type { Review } from '../../../shared/api/types'
import { cx } from '../../../shared/ui/cx'
import { badge, modelName, type BadgeTone } from '../model'

const TONES: Record<BadgeTone, string> = {
  ok: 'bg-sheet text-ink ring-rule',
  fixed: 'bg-wash text-blue-ink ring-blue',
  attention: 'bg-marker text-marker-ink ring-ink',
  accepted: 'bg-sheet text-muted ring-rule',
}

/** The supervisor's word on a panel, on top of it. Hover, focus or tap shows which model checked it. */
export function ReviewBadge({ review }: { review: Review }) {
  const { label, tone } = badge(review)
  const checkedBy = `Checked by ${modelName(review.model)}`
  return (
    <span
      tabIndex={0}
      title={checkedBy}
      aria-label={`${label}. ${checkedBy}`}
      data-testid="review-badge"
      data-outcome={review.outcome}
      className={cx(
        'group/badge absolute top-2 right-2 max-w-[70%] truncate rounded-full px-3 py-1 text-xs font-bold ring-1 focus-visible:outline-2',
        TONES[tone],
      )}
    >
      {tone === 'ok' && <span aria-hidden="true">✓ </span>}
      {label}
      <span className="hidden font-semibold group-hover/badge:inline group-focus/badge:inline"> · {checkedBy}</span>
    </span>
  )
}
