import { cx } from '../../../shared/ui/cx'

const BARS = 12

/** A row of pencil ticks that fill with the speaker's level. Decorative for screen readers: the status says it. */
export function MicMeter({ level, active }: { level: number; active: boolean }) {
  const lit = active ? Math.round(level * BARS) : 0
  return (
    <div className="flex h-6 items-end gap-[3px]" aria-hidden="true" data-testid="mic-meter" data-level={lit}>
      {Array.from({ length: BARS }, (_, i) => (
        <span
          key={i}
          className={cx('w-1.5 rounded-sm transition-[height,background-color] duration-75', i < lit ? 'bg-blue' : 'bg-rule')}
          style={{ height: `${30 + (i / BARS) * 70}%` }}
        />
      ))}
    </div>
  )
}
