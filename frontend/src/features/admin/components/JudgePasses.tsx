import { useId, useState } from 'react'
import { Button } from '../../../shared/ui/Button'
import type { JudgePass, JudgeReserve } from '../api'

const usd = (n: number) => `$${n.toFixed(2)}`

/** Today's judge passes (stories and spend each), and the control that lowers the judges' reserve at once. */
export function JudgePasses({ reserve, passes, onReserve }: { reserve: JudgeReserve; passes: JudgePass[]; onReserve: (usd: number | null) => void }) {
  const id = useId()
  const [value, setValue] = useState('')
  const amount = Number(value)
  const valid = value.trim() !== '' && Number.isFinite(amount) && amount >= 0
  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-2">
      <h2 id={`${id}-title`} className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
        Judge passes today ({passes.length})
      </h2>
      <p className="m-0 text-sm">
        Reserve {usd(reserve.calendar_usd)} a day from the calendar
        {reserve.override_usd !== null ? `, lowered here to ${usd(reserve.override_usd)}` : ''}. Each pass may start {reserve.stories_per_pass_per_day} stories a day.
      </p>
      {passes.length > 0 ? (
        <table className="text-left text-sm">
          <thead>
            <tr>
              <th scope="col">Pass</th>
              <th scope="col">First seen</th>
              <th scope="col">Stories today</th>
              <th scope="col">Spent today</th>
            </tr>
          </thead>
          <tbody>
            {passes.map((p) => (
              <tr key={p.pass_id}>
                <th scope="row" className="font-mono">
                  {p.pass_id}
                </th>
                <td>{new Date(p.first_seen).toLocaleString()}</td>
                <td>{p.stories_today}</td>
                <td>{usd(p.spent_today_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="m-0 text-sm text-muted">No judge has started a story today.</p>
      )}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (valid) onReserve(amount)
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          Lower the judges' reserve to (USD a day)
          <input type="number" min={0} step="0.5" inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value)} className="w-32 rounded border-[1.5px] border-rule bg-paper px-2 py-1" />
        </label>
        <Button size="sm" variant="ink" type="submit" disabled={!valid}>
          Lower now
        </Button>
        {reserve.override_usd !== null && (
          <Button size="sm" variant="quiet" type="button" onClick={() => onReserve(null)}>
            Back to the calendar
          </Button>
        )}
      </form>
    </section>
  )
}
