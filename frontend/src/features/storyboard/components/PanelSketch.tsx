/** Non-photo-blue pencil lines drawing themselves: the "drawing draft" placeholder. */
export function PanelSketch({ animated }: { animated: boolean }) {
  return (
    <svg viewBox="0 0 160 90" className={animated ? 'sketching size-full' : 'size-full'} aria-hidden="true">
      <g fill="none" stroke="var(--blue)" strokeWidth="0.9" strokeLinecap="round" opacity="0.8">
        <path pathLength={1} d="M6 68 C40 66 120 70 154 67" />
        <path pathLength={1} d="M22 68 V30 h26 v38" />
        <path pathLength={1} d="M112 68 V22 h30 v46" />
        <path pathLength={1} d="M78 32 a7 7 0 1 0 0.1 0 M71 44 l-5 22 h24 l-5 -22 z" />
        <path pathLength={1} d="M60 14 l40 0 M64 20 l32 0" />
      </g>
    </svg>
  )
}
