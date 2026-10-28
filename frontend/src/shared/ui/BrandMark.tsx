/** The storyboard-frame mark from the marketing page. */
export function BrandMark({ className = 'size-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 28 28" className={className} aria-hidden="true">
      <rect x="2" y="6" width="24" height="16" rx="2" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <path d="M8 11c2 2 2 4 0 6M12 9c3 3 3 7 0 10" fill="none" stroke="var(--blue)" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="20" cy="14" r="3" fill="var(--marker)" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  )
}
