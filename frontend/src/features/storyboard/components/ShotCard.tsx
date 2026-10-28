import type { Shot } from '../../../shared/api/types'
import { framingLabel, seconds, shotLabel } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'
import type { PanelPhase } from '../store'
import { PanelSketch } from './PanelSketch'

const DRAWING: Record<'draft' | 'final' | 'change', string> = {
  draft: 'Drawing draft…',
  final: 'Drawing final…',
  change: 'Making your change…',
}

function status(phase: PanelPhase): string {
  switch (phase.kind) {
    case 'waiting-cast':
      return 'Waiting for the cast'
    case 'queued':
      return 'In the queue'
    case 'drawing':
      return DRAWING[phase.what]
    case 'ready':
      return `Revision ${phase.revision}`
    case 'failed':
      return 'Not drawn'
    case 'not-drawn':
      return 'Not drawn yet'
  }
}

export function ShotCard({
  shot,
  phase,
  imageSrc,
  names,
  composing = false,
  onOpen,
  onRetry,
}: {
  shot: Shot
  phase: PanelPhase
  imageSrc: string | null
  names: string[]
  composing?: boolean
  onOpen: () => void
  onRetry: () => void
}) {
  const busy = phase.kind === 'drawing' || phase.kind === 'queued'
  const outdated = phase.kind === 'ready' && phase.outdated
  return (
    <li className="arrive flex flex-col" data-testid="shot-card" data-shot={shot.number} data-phase={phase.kind} data-outdated={outdated || undefined}>
      <article aria-labelledby={`shot-${shot.id}`} className="flex flex-col gap-2">
        <div className="frame aspect-video">
          {phase.kind === 'ready' && imageSrc ? (
            <button type="button" onClick={onOpen} className="group block size-full" aria-label={`Edit the panel of shot ${shot.number}`}>
              <img src={imageSrc} alt={`Shot ${shot.number}: ${shot.action}`} className="size-full object-cover" draggable={false} />
              <span className="absolute right-2 bottom-2 rounded-full bg-ink px-3 py-1 text-sm font-semibold text-paper opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
                Edit panel
              </span>
              {(outdated || composing) && (
                <span className="absolute top-2 left-2 rounded-full bg-marker px-3 py-1 text-xs font-bold text-ink ring-1 ring-ink">
                  {composing ? 'Saving your move…' : 'Out of date'}
                </span>
              )}
            </button>
          ) : (
            <div className="grid size-full place-items-center">
              <PanelSketch animated={busy} />
              <p className="absolute inset-x-3 bottom-2 m-0 text-center text-sm font-semibold" aria-live="polite">
                {status(phase)}
              </p>
            </div>
          )}
        </div>
        <header className="flex items-baseline justify-between gap-2 text-sm text-muted tabular">
          <h3 id={`shot-${shot.id}`} className="m-0 text-base font-extrabold text-ink wide">
            Shot {shotLabel(shot.number)}
          </h3>
          <span>
            {framingLabel(shot.framing)} · {seconds(shot.duration_ms)}
          </span>
        </header>
        <p className="m-0 leading-snug">{shot.action}</p>
        {shot.dialogue && <p className="m-0 border-l-2 border-blue pl-2 text-muted italic">“{shot.dialogue}”</p>}
        {names.length > 0 && <p className="m-0 text-xs text-muted">With {names.join(', ')}</p>}
        {phase.kind === 'waiting-cast' && (
          <p className="m-0 text-xs text-muted">Panels are drawn once you approve the cast, so every frame shows the same characters.</p>
        )}
        {outdated && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted">The story changed after this was drawn.</span>
            <Button size="sm" onClick={onRetry}>
              Draw again
            </Button>
          </div>
        )}
        {phase.kind === 'failed' && (
          <div className="flex flex-wrap items-center gap-2 text-sm" role="alert">
            <span className="text-danger">{phase.message}</span>
            <Button size="sm" onClick={onRetry}>
              Draw again
            </Button>
          </div>
        )}
      </article>
    </li>
  )
}
