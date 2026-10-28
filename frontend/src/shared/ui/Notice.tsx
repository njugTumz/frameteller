import type { ReactNode } from 'react'
import { cx } from './cx'

type Tone = 'info' | 'warn' | 'error'

const TONES: Record<Tone, string> = {
  info: 'border-blue bg-wash',
  warn: 'border-marker bg-sheet',
  error: 'border-danger bg-danger-wash',
}

/** A message that says what to do next. Errors are announced to screen readers straight away. */
export function Notice({
  tone = 'info',
  title,
  children,
  action,
  className,
}: {
  tone?: Tone
  title: string
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cx('rounded-md border-l-4 px-4 py-3 text-ink', TONES[tone], className)}
    >
      <p className="m-0 font-semibold">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
      {action && <div className="mt-3 flex flex-wrap gap-2">{action}</div>}
    </div>
  )
}
