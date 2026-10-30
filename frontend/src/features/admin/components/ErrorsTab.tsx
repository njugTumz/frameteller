import { Button } from '../../../shared/ui/Button'
import type { Errors } from '../api'

const heading = 'm-0 text-sm font-bold uppercase tracking-wider text-muted'
const when = (at: string) => new Date(at).toLocaleString()
// Padded, top-aligned cells so long messages wrap inside their column instead of running into the next one.
const cell = 'border-b border-rule px-2 py-1.5 align-top'
/** A streaming call lasts as long as the recording, so its p95 is a session length, not a latency. */
const isSession = (model: string) => model.startsWith('muse-voice-transcribe')

/** What went wrong lately: recent errors, counts by type, model health today, failed jobs and visitors' reports. */
export function ErrorsTab({ errors, onRetry }: { errors: Errors; onRetry: (key: string) => void }) {
  const counts = Object.entries(errors.counts_24h)
  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Last 24 hours" className="flex flex-col gap-2">
        <h2 className={heading}>Last 24 hours</h2>
        {counts.length === 0 ? (
          <p className="m-0 text-sm">No errors in the last 24 hours.</p>
        ) : (
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {counts.map(([code, n]) => (
              <li key={code} className="rounded-md border-[1.5px] border-rule bg-sheet px-3 py-1 text-sm">
                <code>{code}</code> {n}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Model health today" className="flex flex-col gap-2">
        <h2 className={heading}>Model health today</h2>
        {errors.health.length === 0 ? (
          <p className="m-0 text-sm">No model calls yet today.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="text-left text-sm">
              <thead>
                <tr>
                  <th scope="col" className={cell}>Model</th>
                  <th scope="col" className={cell}>Calls</th>
                  <th scope="col" className={cell}>Failures</th>
                  <th scope="col" className={cell}>Retries</th>
                  <th scope="col" className={cell}>p95</th>
                </tr>
              </thead>
              <tbody>
                {errors.health.map((h) => (
                  <tr key={h.model}>
                    <th scope="row" className={`${cell} whitespace-nowrap font-semibold`}>{h.model}</th>
                    <td className={cell}>{h.calls}</td>
                    <td className={cell}>{h.failures}</td>
                    <td className={cell}>{h.retries}</td>
                    <td className={`${cell} whitespace-nowrap`}>
                      {h.p95_ms === null ? '–' : `${(h.p95_ms / 1000).toFixed(1)}s ${isSession(h.model) ? 'session length' : 'latency'}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-label="Failed jobs" className="flex flex-col gap-2">
        <h2 className={heading}>Failed jobs ({errors.failed_jobs.length})</h2>
        <p className="m-0 text-xs text-muted">A retry runs on the public budget, and is refused while the studio is paused or full.</p>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {errors.failed_jobs.map((j) => (
            <li key={j.key} className="flex flex-wrap items-center justify-between gap-2 rounded-md border-[1.5px] border-rule bg-sheet p-3 text-sm" data-testid="failed-job">
              <span>
                <strong>{j.kind}</strong> · {j.component} · <code>{j.code}</code> · {j.message}
                <span className="block text-xs text-muted">
                  {when(j.at)} · project {j.project_id ?? '–'}
                  {j.retries > 0 ? ` · retried ${j.retries}×` : ''}
                </span>
              </span>
              <Button size="sm" onClick={() => onRetry(j.key)} aria-label={`Retry ${j.key}`}>
                Retry
              </Button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Reported problems" className="flex flex-col gap-2">
        <h2 className={heading}>Reported problems ({errors.reports.length})</h2>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {errors.reports.map((r) => (
            <li key={r.id} className="rounded-md border-[1.5px] border-rule bg-sheet p-3 text-sm">
              {r.text || <em className="text-muted">(no words)</em>}
              <span className="block text-xs text-muted">
                {when(r.at)} · project {r.project_id} · visitor {r.visitor ?? '–'}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Recent errors" className="flex flex-col gap-2">
        <h2 className={heading}>Recent errors ({errors.recent.length})</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[56rem] table-fixed text-left text-sm">
            <colgroup>
              <col className="w-44" />
              <col className="w-28" />
              <col />
              <col className="w-48" />
              <col className="w-40" />
              <col className="w-32" />
            </colgroup>
            <thead>
              <tr>
                <th scope="col" className={cell}>Time</th>
                <th scope="col" className={cell}>Component</th>
                <th scope="col" className={cell}>Message</th>
                <th scope="col" className={cell}>Code</th>
                <th scope="col" className={cell}>Project</th>
                <th scope="col" className={cell}>Visitor</th>
              </tr>
            </thead>
            <tbody>
              {errors.recent.map((e, i) => (
                <tr key={`${e.at}-${i}`} data-testid="incident">
                  <td className={`${cell} whitespace-nowrap`}>{when(e.at)}</td>
                  <td className={`${cell} break-words`}>{e.component}</td>
                  <td className={`${cell} break-words`}>{e.message}</td>
                  <td className={`${cell} break-all`}>
                    <code>{e.code}</code>
                  </td>
                  <td className={`${cell} break-all font-mono text-xs`}>{e.project_id ?? '–'}</td>
                  <td className={`${cell} break-all`}>
                    <code>{e.visitor ?? '–'}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
