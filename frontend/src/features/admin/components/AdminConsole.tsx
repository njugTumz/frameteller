import { useState } from 'react'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
import type { AdminAction, AdminEntry, Overview } from '../api'
import { JudgePasses } from './JudgePasses'

const usd = (n: number) => `$${n.toFixed(2)}`

/** Today's budgets and queues, then every gallery entry with the actions it allows. */
export function AdminConsole({
  overview,
  entries,
  error,
  onAct,
  onWatch,
  onReserve,
}: {
  overview: Overview | null
  entries: AdminEntry[] | null
  error: string | null
  onAct: (id: string, action: AdminAction | 'remove') => void
  onWatch: (id: string) => Promise<string>
  onReserve: (usd: number | null) => void
}) {
  const [videos, setVideos] = useState<Record<string, string>>({})
  const pending = entries?.filter((e) => e.status === 'pending' || e.reports.length > 0) ?? []
  const rest = entries?.filter((e) => !pending.includes(e)) ?? []
  const row = (e: AdminEntry) => (
    <li key={e.id} className="flex flex-col gap-2 rounded-md border-[1.5px] border-rule bg-sheet p-3" data-testid="admin-entry">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <strong>{e.title}</strong>
        <span className="text-sm text-muted">
          {e.status}
          {e.featured ? ' · featured' : ''} · {e.style} · audio {e.audio} · ♥ {e.hearts}
        </span>
      </div>
      {e.note && <p className="m-0 text-sm">{e.note}</p>}
      {e.reviewed_by && <p className="m-0 text-xs text-muted">Checked by {e.reviewed_by}</p>}
      {e.reports.length > 0 && (
        <ul className="m-0 pl-5 text-sm">
          {e.reports.map((r) => (
            <li key={r.at}>
              {r.reason || '(no reason)'} <span className="text-muted">{new Date(r.at).toLocaleString()}</span>
            </li>
          ))}
        </ul>
      )}
      {videos[e.id] && <video src={videos[e.id]} controls className="w-full max-w-xl" aria-label={`${e.title}, the gallery video`} />}
      <div className="flex flex-wrap gap-2">
        {e.has_video && !videos[e.id] && (
          <Button size="sm" onClick={() => void onWatch(e.id).then((url) => setVideos((v) => ({ ...v, [e.id]: url })))}>
            Watch
          </Button>
        )}
        <a className="self-center text-sm underline" href={`/s/${e.share_token}`} target="_blank" rel="noreferrer">
          Share page
        </a>
        {e.status !== 'published' && e.has_video && (
          <Button size="sm" variant="ink" onClick={() => onAct(e.id, 'publish')}>
            Publish
          </Button>
        )}
        {e.status === 'published' && (
          <Button size="sm" onClick={() => onAct(e.id, e.featured ? 'unfeature' : 'feature')}>
            {e.featured ? 'Unfeature' : 'Feature'}
          </Button>
        )}
        {e.status !== 'hidden' && (
          <Button size="sm" onClick={() => onAct(e.id, 'hide')}>
            Hide
          </Button>
        )}
        <Button size="sm" variant="quiet" onClick={() => window.confirm(`Remove “${e.title}” for good?`) && onAct(e.id, 'remove')}>
          Remove
        </Button>
      </div>
    </li>
  )
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-6">
      <h1 className="m-0 text-2xl font-bold">Admin</h1>
      {error && <Notice tone="error" title={error} />}
      {overview && (
        <section aria-label="Today" className="flex flex-col gap-2">
          <h2 className="m-0 text-sm font-bold uppercase tracking-wider text-muted">Today</h2>
          <ul className="m-0 flex list-none flex-wrap gap-3 p-0">
            {overview.budgets.map((b) => (
              <li key={b.lane} className="rounded-md border-[1.5px] border-rule bg-sheet px-3 py-2 text-sm">
                <strong>{b.lane}</strong> {b.day}: {usd(b.spent_usd)} of {usd(b.cap_usd)} ({usd(b.left_usd)} left)
              </li>
            ))}
          </ul>
          <p className="m-0 text-sm">
            {overview.live_sessions} live sessions · {overview.paused ? 'PAUSED · ' : ''}Read it to me {overview.read_it_to_me ? 'on' : 'off'} · judge pass{' '}
            {overview.judge_pass ? 'on' : 'off'} · Glimmer {overview.glimmer_warm_until ? `warm until ${overview.glimmer_warm_until}` : 'cold'}
          </p>
          <table className="text-left text-sm">
            <thead>
              <tr>
                <th scope="col">Queue</th>
                <th scope="col">In flight</th>
                <th scope="col">Waiting</th>
                <th scope="col">Longest wait</th>
                <th scope="col">Hold</th>
              </tr>
            </thead>
            <tbody>
              {overview.gates.map((g) => (
                <tr key={g.name}>
                  <th scope="row">{g.name}</th>
                  <td>
                    {g.in_flight}/{g.limit}
                  </td>
                  <td>{g.waiting}</td>
                  <td>{g.longest_wait_s}s</td>
                  <td>{g.hold_s}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {overview?.judge_pass && <JudgePasses reserve={overview.judge_reserve} passes={overview.judge_passes} onReserve={onReserve} />}
      {entries && (
        <section aria-label="Gallery" className="flex flex-col gap-3">
          <h2 className="m-0 text-sm font-bold uppercase tracking-wider text-muted">Needs a look ({pending.length})</h2>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">{pending.map(row)}</ul>
          <h2 className="m-0 text-sm font-bold uppercase tracking-wider text-muted">Everything else ({rest.length})</h2>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">{rest.map(row)}</ul>
        </section>
      )}
    </div>
  )
}
