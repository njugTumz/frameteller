import type { ReactNode } from 'react'

export function StyleCard({
  value,
  checked,
  title,
  note,
  art,
  onSelect,
}: {
  value: string
  checked: boolean
  title: string
  note: string
  art: ReactNode
  onSelect: () => void
}) {
  return (
    <label className="group relative flex cursor-pointer flex-col gap-2 rounded-md border-2 border-rule bg-sheet p-3 has-checked:border-ink has-checked:shadow-[4px_4px_0_var(--ink)] has-focus-visible:outline-3 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus">
      <input type="radio" name="style" value={value} checked={checked} onChange={onSelect} className="sr-only" />
      <div className="frame aspect-video">{art}</div>
      <span className="flex items-center justify-between font-bold">
        {title}
        <span aria-hidden="true" className="size-4 rounded-full border-2 border-ink group-has-checked:bg-marker" />
      </span>
      <span className="text-sm text-muted">{note}</span>
    </label>
  )
}

/** Small drawings of each preset, in the marketing page's line style. */
export function PencilArt() {
  return (
    <svg viewBox="0 0 160 90" className="size-full" aria-hidden="true">
      <g fill="none" stroke="var(--blue)" strokeWidth="1" strokeLinecap="round">
        <path d="M0 70h160M20 70V30h30v40M110 70V20h35v50" />
        <path d="M24 36h8M24 44h8M114 28h10M114 38h10" />
      </g>
      <g fill="none" stroke="var(--ink)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="78" cy="38" r="6" />
        <path d="M72 46l-4 22h22l-4-22z" fill="var(--marker)" />
        <path d="M74 68v8M84 68v8" />
      </g>
    </svg>
  )
}

export function CutoutArt() {
  return (
    <svg viewBox="0 0 160 90" className="size-full" aria-hidden="true">
      <rect width="160" height="90" fill="var(--wash)" />
      <path d="M0 64l30-6 40 5 50-7 40 4v30H0z" fill="var(--blue)" opacity="0.55" />
      <path d="M18 64V34l16-4 2 34z" fill="var(--rule)" stroke="var(--ink)" strokeWidth="0.8" />
      <path d="M112 62V22l28 2v38z" fill="var(--rule)" stroke="var(--ink)" strokeWidth="0.8" />
      <g transform="translate(2 2)" opacity="0.25">
        <path d="M70 46l-4 22h24l-5-22z" fill="var(--ink)" />
      </g>
      <path d="M70 46l-4 22h24l-5-22z" fill="var(--marker)" stroke="var(--ink)" strokeWidth="0.8" />
      <circle cx="78" cy="38" r="7" fill="var(--sheet)" stroke="var(--ink)" strokeWidth="0.8" />
    </svg>
  )
}
