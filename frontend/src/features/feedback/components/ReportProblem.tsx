import { useState } from 'react'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
import { MAX_REPORT } from '../limits'
import type { ReportState } from '../hooks/useReportProblem'

/** A quiet "Report a problem" link that opens a short form. The project's id goes with it; nothing else. */
export function ReportProblem({
  state,
  error,
  onSend,
  onReset,
}: {
  state: ReportState
  error: string | null
  onSend: (text: string) => void
  onReset: () => void
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  if (!open)
    return (
      <Button size="sm" variant="quiet" className="self-start" onClick={() => setOpen(true)}>
        Report a problem
      </Button>
    )
  if (state === 'sent')
    return (
      <div className="flex flex-col gap-2">
        <Notice tone="info" title="Thanks, we got your report." />
        <Button
          size="sm"
          variant="quiet"
          className="self-start"
          onClick={() => {
            setText('')
            setOpen(false)
            onReset()
          }}
        >
          Close
        </Button>
      </div>
    )
  return (
    <form
      className="flex flex-col gap-2 rounded-md border-[1.5px] border-rule bg-sheet p-3"
      onSubmit={(e) => {
        e.preventDefault()
        onSend(text)
      }}
    >
      <label htmlFor="problem-text" className="text-sm font-bold">
        What went wrong? <span className="font-normal text-muted">(optional)</span>
      </label>
      <textarea
        id="problem-text"
        value={text}
        maxLength={MAX_REPORT}
        rows={3}
        onChange={(e) => setText(e.target.value)}
        className="rounded-md border-[1.5px] border-rule bg-paper p-2 text-sm"
      />
      <p className="m-0 text-xs text-muted">
        {text.length}/{MAX_REPORT} · this story's id is sent with it, so we can look. Reports are deleted after 30 days.
      </p>
      {error && <Notice tone="error" title={error} />}
      <div className="flex gap-2">
        <Button size="sm" variant="ink" type="submit" disabled={state === 'sending'}>
          {state === 'sending' ? 'Sending…' : 'Send report'}
        </Button>
        <Button size="sm" variant="quiet" type="button" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
