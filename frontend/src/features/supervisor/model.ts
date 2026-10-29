import type { Review } from '../../shared/api/types'

/** "muse-glimmer" → "Muse Glimmer", "muse-spark-1.3" → "Muse Spark". */
export function modelName(model: string): string {
  if (model.startsWith('muse-glimmer')) return 'Muse Glimmer'
  if (model.startsWith('muse-spark')) return 'Muse Spark'
  return model
}

export type BadgeTone = 'ok' | 'fixed' | 'attention' | 'accepted'

/** What a panel's badge says, from the supervisor's review. */
export function badge(review: Review): { label: string; tone: BadgeTone } {
  switch (review.outcome) {
    case 'checked':
      return { label: 'Checked', tone: 'ok' }
    case 'fixed':
      return { label: review.summary.startsWith('Fixed') ? review.summary : `Fixed: ${review.summary}`, tone: 'fixed' }
    case 'needs_user':
      return { label: 'Needs your eye', tone: 'attention' }
    case 'accepted':
      return { label: 'Accepted', tone: 'accepted' }
  }
}

/** Serious issues first: the ones the policy acts on. */
export function seriousIssues(review: Review) {
  return review.issues.filter((i) => i.severity !== 'minor')
}
