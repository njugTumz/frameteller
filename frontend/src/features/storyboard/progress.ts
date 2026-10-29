import type { Shot } from '../../shared/api/types'
import type { PanelJob } from './store'

/**
 * One line saying what the studio is doing for the whole storyboard: "Drawing shot 3 of 6…" while panels draw,
 * "Checking continuity…" while the supervisor reviews new ones, "All 6 shots are drawn." when done.
 */
export function boardProgress(shots: Shot[], jobs: Record<string, PanelJob>, awaitingReview: Record<string, number>): string | null {
  if (shots.length === 0) return null
  const total = shots.length
  const drawn = shots.filter((s) => s.panel?.status === 'ready').length
  const busy = shots.filter((s) => {
    const job = jobs[s.id]
    return job?.status === 'queued' || job?.status === 'running' || s.panel?.status === 'pending'
  }).length
  if (busy > 0) {
    const next = Math.min(drawn + 1, total)
    return busy > 1 ? `Drawing shots ${next}–${Math.min(drawn + busy, total)} of ${total}…` : `Drawing shot ${next} of ${total}…`
  }
  if (Object.keys(awaitingReview).length > 0) return 'Checking continuity…'
  if (drawn === total) return `All ${total} shots are drawn.`
  return null
}
