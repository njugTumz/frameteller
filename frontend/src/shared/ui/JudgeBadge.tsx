/** Shown in the top bar while this browser has a valid judge pass. */
export function JudgeBadge() {
  return (
    <span className="rounded-full bg-marker px-3 py-1 text-xs font-extrabold text-ink ring-1 ring-ink" data-testid="judge-badge" title="You skip the public queue and limits">
      Judge access
    </span>
  )
}
