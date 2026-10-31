import { useState } from 'react'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
import { byline } from '../../../shared/creator'
import { OfficialBadge } from '../../../shared/ui/OfficialBadge'
import { cx } from '../../../shared/ui/cx'
import type { AdminAction, AdminEntry, Errors, JudgeGlimmer, Overview } from '../api'
import { ErrorsTab } from './ErrorsTab'
import { JudgePasses } from './JudgePasses'

const usd = (n: number) => `$${n.toFixed(2)}`

type Tab = 'overview' | 'errors'

/** Overview: today's budgets and queues, then every gallery entry with the actions it allows. Errors: what went wrong. */
export function AdminConsole({
  overview,
  entries,
  errors,
  error,
  onAct,
  onSign,
  onWatch,
  onReserve,
  onRetry,
}: {
  overview: Overview | null
  entries: AdminEntry[] | null
  errors: Errors | null
  error: string | null
  onAct: (id: string, action: AdminAction | 'remove') => void
  onSign: (id: string, name: string, country: string) => void
  onWatch: (id: string) => Promise<string>
  onReserve: (usd: number | null) => void
  onRetry: (key: string) => void
}) {
  const [tab, setTab] = useState<Tab>('overview')
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
      <EntrySignature entry={e} onSign={(name, country) => onSign(e.id, name, country)} />
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
        <a className="self-center text-sm underline pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center" href={`/s/${e.share_token}`} target="_blank" rel="noreferrer">
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
      <div role="tablist" aria-label="Admin" className="flex gap-2 border-b-[1.5px] border-rule">
        {(['overview', 'errors'] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cx('-mb-[1.5px] border-b-[3px] px-3 py-2 text-sm font-bold pointer-coarse:min-h-11', tab === t ? 'border-ink' : 'border-transparent text-muted')}
          >
            {t === 'overview' ? 'Overview' : `Errors${errors ? ` (${errors.recent.length})` : ''}`}
          </button>
        ))}
      </div>
      {tab === 'errors' && (errors ? <ErrorsTab errors={errors} onRetry={onRetry} /> : <p className="m-0 text-sm">Loading…</p>)}
      {tab === 'overview' && overview && (
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
          {overview.judge_glimmer && <JudgeGlimmerLine glimmer={overview.judge_glimmer} />}
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
      {tab === 'overview' && overview?.judge_pass && <JudgePasses reserve={overview.judge_reserve} passes={overview.judge_passes} onReserve={onReserve} />}
      {tab === 'overview' && entries && (
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

/** How the entry is signed, and a form to change it. Signed here, a reserved name ("Frameteller team") is official. */
export function EntrySignature({ entry, onSign }: { entry: AdminEntry; onSign: (name: string, country: string) => void }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(entry.creator.name)
  const [country, setCountry] = useState(entry.creator.country)
  if (!editing)
    return (
      <p className="m-0 flex flex-wrap items-center gap-2 text-sm" data-testid="admin-byline">
        <span>
          {byline(entry.creator)}
          {entry.creator.official && <OfficialBadge />}
        </span>
        {entry.status !== 'checking' && (
          <Button
            size="sm"
            variant="quiet"
            onClick={() => {
              setName(entry.creator.name)
              setCountry(entry.creator.country)
              setEditing(true)
            }}
          >
            Edit name
          </Button>
        )}
      </p>
    )
  return (
    <form
      className="flex flex-wrap items-end gap-2 text-sm"
      onSubmit={(ev) => {
        ev.preventDefault()
        onSign(name.trim(), country.trim().toUpperCase())
        setEditing(false)
      }}
    >
      <label className="flex flex-col gap-1">
        Name
        <input value={name} maxLength={40} onChange={(ev) => setName(ev.target.value)} className="rounded border-[1.5px] border-rule bg-paper px-2 py-1" />
      </label>
      <label className="flex flex-col gap-1">
        Country code
        <input
          value={country}
          maxLength={2}
          pattern="[A-Za-z]{2}"
          placeholder="none"
          onChange={(ev) => setCountry(ev.target.value)}
          className="w-24 rounded border-[1.5px] border-rule bg-paper px-2 py-1"
        />
      </label>
      <Button size="sm" variant="ink" type="submit">
        Save
      </Button>
      <Button size="sm" variant="quiet" onClick={() => setEditing(false)}>
        Cancel
      </Button>
    </form>
  )
}

/** Judges wake Glimmer (ADR 0020): today's wake-ups against the cap, its state, and the estimated Modal cost. */
export function JudgeGlimmerLine({ glimmer: g }: { glimmer: JudgeGlimmer }) {
  const state = g.waking ? 'waking' : g.warm ? 'warm' : 'cold'
  return (
    <p className="m-0 text-sm" data-testid="judge-glimmer">
      Judge wake-ups today: {g.wakes} of {g.wakes_cap} · Glimmer {state}
      {g.last_cold_start_s !== null ? ` · last cold start ${Math.round(g.last_cold_start_s)} s` : ''} · Modal today ≈ $
      {g.estimated_usd.toFixed(2)} of ${g.usd_cap.toFixed(2)}
    </p>
  )
}
