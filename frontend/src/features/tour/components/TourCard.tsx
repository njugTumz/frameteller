import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '../../../shared/ui/Button'
import type { StepView } from '../machine'
import type { TourStep } from '../steps'

const GAP = 12
const EDGE = 16
const WIDE = 640 // below this the card docks at the bottom of the screen

/** One step of the tour: a non-modal card next to the element it explains, with the element outlined. */
export function TourCard({
  step,
  view,
  rect,
  layer,
  onNext,
  onBack,
  onSkip,
  onAction,
}: {
  step: TourStep
  view: StepView
  rect: DOMRect | null
  layer: HTMLElement | null
  onNext: () => void
  onBack: () => void
  onSkip: () => void
  onAction: () => void
}) {
  const id = useId()
  const card = useRef<HTMLElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const [size, setSize] = useState({ width: 360, height: 200 })
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight })

  useEffect(() => heading.current?.focus({ preventScroll: true }), [step.id]) // managed focus: each step reads from its title
  useEffect(() => {
    const el = card.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => setSize({ width: el.offsetWidth, height: el.offsetHeight }))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    const resize = () => setViewport({ width: window.innerWidth, height: window.innerHeight })
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])

  const docked = viewport.width < WIDE || !rect
  let style: CSSProperties
  if (docked) {
    style = rect || viewport.width < WIDE ? { left: EDGE, right: EDGE, bottom: EDGE } : { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' }
  } else {
    const below = rect.bottom + GAP
    const above = rect.top - GAP - size.height
    const top = below + size.height <= viewport.height - EDGE ? below : above >= EDGE ? above : viewport.height - size.height - EDGE
    const left = Math.min(Math.max(rect.left, EDGE), viewport.width - size.width - EDGE)
    style = { top, left }
  }

  const keys = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault() // inside the panel editor, Esc closes the tour, not the editor
      e.stopPropagation()
      onSkip()
    }
  }
  const finishing = step.action?.kind === 'narrate'

  const content = (
    <>
      {rect && (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed z-[60] rounded-md outline-3 outline-offset-4 outline-marker motion-safe:transition-all motion-safe:duration-200"
          style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }}
          data-testid="tour-highlight"
        />
      )}
      <section
        ref={card}
        role="dialog"
        aria-modal="false"
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-text`}
        onKeyDown={keys}
        className="fixed z-[61] flex max-w-[min(360px,calc(100vw-32px))] flex-col gap-2 rounded-md border-2 border-ink bg-paper p-4 text-ink shadow-xl motion-safe:transition-[top,left] motion-safe:duration-200"
        style={style}
        data-testid="tour-card"
        data-step={step.id}
        data-phase={view.phase}
      >
        <p className="m-0 text-xs font-bold uppercase tracking-wider text-muted">
          Tour · <span data-testid="tour-progress">{view.progress}</span>
        </p>
        <h2 id={`${id}-title`} ref={heading} tabIndex={-1} className="m-0 text-lg font-extrabold leading-tight outline-none">
          {view.phase === 'waiting' || view.phase === 'blocked' ? 'One moment' : step.title}
        </h2>
        <div id={`${id}-text`} aria-live="polite" className="flex flex-col gap-1">
          <p className="m-0 text-sm">
            {view.phase === 'waiting' && (
              <span aria-hidden="true" className="mr-1.5 inline-block size-2 rounded-full bg-marker motion-safe:animate-pulse" />
            )}
            {view.text}
          </p>
          {view.hint && <p className="m-0 text-sm font-semibold">{view.hint}</p>}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {view.canBack && (
            <Button size="sm" onClick={onBack}>
              Back
            </Button>
          )}
          <Button size="sm" variant="quiet" onClick={finishing ? onNext : onSkip}>
            {finishing ? 'Done' : 'Skip tour'}
          </Button>
          <span className="flex-1" />
          {step.action ? (
            <Button size="sm" variant="ink" onClick={onAction} disabled={!view.canNext}>
              {step.action.label}
            </Button>
          ) : (
            <Button size="sm" variant="ink" onClick={onNext} disabled={!view.canNext}>
              Next
            </Button>
          )}
        </div>
      </section>
    </>
  )
  return createPortal(content, layer ?? document.body)
}
