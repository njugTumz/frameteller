import type { ReactNode } from 'react'
import type { Shot } from '../../../shared/api/types'
import { framingLabel, inLine, seconds, shotLabel } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'
import { DrawingOverlay, RedrawControl, type RedrawChoice } from '../../../shared/ui/Redraw'
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
      return phase.position ? `Busy studio. ${inLine(phase.position, phase.estimateS ?? 0)}` : 'In the queue'
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
  badge,
  review,
  previousSrc = null,
  choice = null,
  onOpen,
  onRedraw,
  onDelete,
}: {
  shot: Shot
  phase: PanelPhase
  imageSrc: string | null
  names: string[]
  composing?: boolean
  /** On top of a ready panel: the continuity supervisor's badge. */
  badge?: ReactNode
  /** Under the shot: what the supervisor wants the user to look at. */
  review?: ReactNode
  /** The drawing being replaced while a redraw runs, or that stays after it failed. */
  previousSrc?: string | null
  /** After a Redraw: the drawing it replaced, to keep instead (ADR 0022). */
  choice?: { previousSrc: string | null; busy: boolean; error?: string | null; onUseNew: () => void; onKeepPrevious: () => void } | null
  onOpen: () => void
  /** Redraw, with what should change or Surprise me: on every drawn panel, and after a failure. */
  onRedraw: (choice: RedrawChoice) => void
  /** "Delete shot", with Undo. */
  onDelete?: () => void
}) {
  const busy = phase.kind === 'drawing' || phase.kind === 'queued'
  const outdated = phase.kind === 'ready' && phase.outdated
  const failed = phase.kind === 'failed' ? phase : null
  // A drawn panel keeps its drawing on screen while it is drawn again, and after that fails.
  const keep = (busy || failed) && previousSrc
  const canRedraw = phase.kind === 'ready' || phase.kind === 'failed'
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
              {badge}
              {(outdated || composing) && (
                <span className="absolute top-2 left-2 rounded-full bg-marker px-3 py-1 text-xs font-bold text-ink ring-1 ring-ink">
                  {composing ? 'Saving your move…' : 'Out of date'}
                </span>
              )}
            </button>
          ) : keep ? (
            <div className="relative size-full">
              <img src={previousSrc} alt={`Shot ${shot.number}: ${shot.action} (the drawing before)`} className="size-full object-cover" draggable={false} />
              {busy && <DrawingOverlay label={phase.kind === 'queued' ? status(phase) : 'Drawing… about 20 s'} />}
            </div>
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
        {onDelete && (
          <Button variant="quiet" size="sm" className="self-start px-1 text-muted" onClick={onDelete} aria-label={`Delete shot ${shot.number}`}>
            Delete shot
          </Button>
        )}
        {phase.kind === 'ready' && review}
        {phase.kind === 'waiting-cast' && (
          <p className="m-0 text-xs text-muted">Panels are drawn once you approve the cast, so every frame shows the same characters.</p>
        )}
        {choice && (
          <div className="flex flex-col gap-2 rounded-md border-[1.5px] border-ink bg-sheet p-2 text-sm" role="group" aria-label={`New drawing of shot ${shot.number}`} data-testid="redraw-choice">
            <div className="flex items-center gap-2">
              {choice.previousSrc && <img src={choice.previousSrc} alt="The drawing before" className="h-10 w-15 rounded-sm border border-rule object-cover" />}
              <span className="font-semibold">Here’s the new drawing. Keep it?</span>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="ink" disabled={choice.busy} onClick={choice.onUseNew}>
                Use new
              </Button>
              <Button size="sm" disabled={choice.busy} onClick={choice.onKeepPrevious}>
                {choice.busy ? 'Bringing it back…' : 'Keep previous'}
              </Button>
            </div>
            {choice.error && (
              <p className="m-0 text-danger" role="alert">
                {choice.error}
              </p>
            )}
          </div>
        )}
        {outdated && <p className="m-0 text-sm text-muted">The story changed after this was drawn. Redraw it to match.</p>}
        {failed && (
          <div className="flex flex-col gap-1 text-sm" role="alert">
            <span className="text-danger">{failed.message}</span>
            {failed.suggestion && (
              <span className="text-muted">
                Suggested change: <q className="font-semibold text-ink">{failed.suggestion}</q>
              </span>
            )}
          </div>
        )}
        {canRedraw && (
          <RedrawControl
            key={failed?.suggestion ?? 'redraw'}
            subject={`shot ${shot.number}`}
            initialChange={failed?.suggestion ?? ''}
            initiallyOpen={!!failed?.suggestion}
            onRedraw={onRedraw}
          />
        )}
      </article>
    </li>
  )
}
