import { useId, useState } from 'react'
import { Button } from './Button'
import { cx } from './cx'

/** What the user asked of a Redraw (ADR 0022): an optional change, or a bolder new take. */
export interface RedrawChoice {
  change: string
  surprise: boolean
}

export const MAX_CHANGE_CHARS = 300

export function RedrawIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className={cx('size-4 shrink-0', className)} fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 10a6 6 0 1 1-1.8-4.3" />
      <path d="M16 3.5v3.7h-3.7" />
    </svg>
  )
}

/**
 * The Redraw button on every panel and sheet. It opens a small box, "What should change?", which may stay
 * empty: Redraw draws a new take, Surprise me a bolder one.
 */
export function RedrawControl({
  subject,
  disabled = false,
  examples = 'e.g. “make it night”, “show her face closer”',
  initialChange = '',
  initiallyOpen = false,
  surprise = true,
  requireChange = false,
  className,
  onRedraw,
}: {
  /** What is redrawn, for screen readers: "shot 3", "Mira's sheet". */
  subject: string
  disabled?: boolean
  examples?: string
  /** A suggested change to start from (after a refusal). */
  initialChange?: string
  initiallyOpen?: boolean
  /** Offer Surprise me. */
  surprise?: boolean
  /** The same drawing was refused: a Redraw needs a change (409 edit_first otherwise). */
  requireChange?: boolean
  className?: string
  onRedraw: (choice: RedrawChoice) => void
}) {
  const id = useId()
  const [open, setOpen] = useState(initiallyOpen)
  const [change, setChange] = useState(initialChange)
  const send = (choice: RedrawChoice) => {
    onRedraw(choice)
    setOpen(false)
    setChange('')
  }
  if (!open) {
    return (
      <Button size="sm" className={cx('self-start', className)} disabled={disabled} onClick={() => (setChange(initialChange), setOpen(true))} aria-label={`Redraw ${subject}`} data-testid="redraw">
        <RedrawIcon />
        Redraw
      </Button>
    )
  }
  return (
    <form
      className={cx('flex flex-col gap-2 rounded-md border-[1.5px] border-ink bg-paper p-2 text-sm', className)}
      aria-label={`Redraw ${subject}`}
      data-testid="redraw-box"
      onSubmit={(e) => {
        e.preventDefault()
        send({ change: change.trim(), surprise: false })
      }}
    >
      <label htmlFor={id} className="font-bold">
        What should change? {!requireChange && <span className="font-normal text-muted">(optional)</span>}
      </label>
      <input
        id={id}
        value={change}
        autoFocus
        maxLength={MAX_CHANGE_CHARS}
        placeholder={examples}
        onChange={(e) => setChange(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && (e.stopPropagation(), e.preventDefault(), setOpen(false))}
        className="min-w-0 rounded border-[1.5px] border-rule bg-paper px-2 py-1.5 focus:border-ink"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ink" type="submit" disabled={disabled || (requireChange && !change.trim())}>
          <RedrawIcon />
          Redraw
        </Button>
        {surprise && (
          <Button size="sm" disabled={disabled} onClick={() => send({ change: change.trim(), surprise: true })}>
            Surprise me
          </Button>
        )}
        <Button size="sm" variant="quiet" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

/** Over the drawing being replaced: it stays visible while the new one is drawn (about 20 s at p50). */
export function DrawingOverlay({ label = 'Drawing… about 20 s' }: { label?: string }) {
  return (
    <div className="pointer-events-none absolute inset-0 flex flex-col justify-end bg-paper/45" data-testid="drawing-overlay">
      <p className="m-2 self-start rounded-full bg-ink px-3 py-1 text-sm font-semibold text-paper" role="status" aria-live="polite">
        {label}
      </p>
      <div className="h-1.5 w-full overflow-hidden bg-rule" aria-hidden="true">
        <div className="drawing-progress h-full bg-blue" />
      </div>
    </div>
  )
}
