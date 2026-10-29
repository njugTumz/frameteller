import type { SupervisorEntry } from '../../../shared/api/types'
import { cx } from '../../../shared/ui/cx'
import { modelName } from '../model'

const MARK: Record<SupervisorEntry['outcome'], string> = {
  checked: '✓',
  fixed: '✎',
  needs_user: '!',
  accepted: '·',
}

/**
 * The supervisor's decisions in order, newest last: "Shot 4: remove the blue vest (CONT-04, …). Fixed in 1 try."
 * The switch turns the checks on or off for this project.
 */
export function SupervisorFeed({
  entries,
  enabled,
  busy,
  error,
  onToggle,
}: {
  entries: SupervisorEntry[]
  enabled: boolean
  busy: boolean
  error: string | null
  onToggle: (enabled: boolean) => void
}) {
  return (
    <section aria-labelledby="supervisor-title" className="flex flex-col gap-3 rounded-md border border-rule bg-sheet p-4" data-testid="supervisor-feed">
      <div className="flex items-center justify-between gap-3">
        <h2 id="supervisor-title" className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
          Supervisor
        </h2>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} disabled={busy} onChange={(e) => onToggle(e.target.checked)} className="size-4 accent-ink" />
          Continuity checks
        </label>
      </div>
      {error && (
        <p className="m-0 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      {entries.length === 0 ? (
        <p className="m-0 text-sm text-muted">
          {enabled
            ? 'An agent checks every reference sheet and panel against the cast and the shot, fixes what it can in drafts, and asks you about the rest.'
            : 'Checks are off: new sheets and panels are not reviewed.'}
        </p>
      ) : (
        <ol className="m-0 flex max-h-72 list-none flex-col gap-2 overflow-y-auto p-0 text-sm" aria-live="polite">
          {entries.map((e) => (
            <li key={`${e.at}-${e.message}`} className="flex gap-2" data-outcome={e.outcome}>
              <span aria-hidden="true" className={cx('w-4 shrink-0 text-center font-bold', e.outcome === 'needs_user' ? 'text-danger' : 'text-muted')}>
                {MARK[e.outcome]}
              </span>
              <span>
                {e.message} <span className="text-xs text-muted">({modelName(e.model)})</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
