import { useEffect, useRef, type ReactNode } from 'react'
import type { Mask, Shot } from '../../../shared/api/types'
import { framingLabel, seconds, shotLabel } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
import { DrawingOverlay, RedrawControl, type RedrawChoice } from '../../../shared/ui/Redraw'
import type { Snapshot } from '../store'

export interface EditorView {
  shot: Shot
  revision: number
  drawing: 'draft' | 'final' | 'change' | null
  failed: string | null
  selection: { mask: Mask; cached: boolean; ms: number } | null
  selecting: boolean
  selectError: string | null
  masks: Mask[]
  hasMoves: boolean
  before: Snapshot | null
  showBefore: boolean
  beforeSrc: string | null
  editError: string | null
  /** A saved move is being composited on a clean plate. */
  preparing?: boolean
  /** Earlier drawings, newest first: Use this shows one again (ADR 0022). */
  versions?: { revision: number; src: string }[]
  /** After a Redraw: the drawing it replaced, until Use new or Keep previous. */
  redrawnFrom?: number | null
  /** The version being brought back, and why that failed. */
  restoring?: number | null
  restoreError?: string | null
  /** After a refusal: the plainer change to start the Redraw box from. */
  suggestion?: string | null
}

const DRAWING = { draft: 'Drawing… about 20 s', final: 'Drawing the final panel… about 20 s', change: 'Making your change… about 20 s' } as const

/** The panel editor: a modal over the studio. Esc or Close returns to the storyboard. */
export function PanelEditor({
  view,
  canvas,
  editBox,
  onClose,
  onSelectMask,
  onResetMoves,
  onToggleBefore,
  onDrawFinal,
  onRedraw,
  onUseVersion,
  onUseNew,
}: {
  view: EditorView
  canvas: ReactNode
  editBox: ReactNode
  onClose: () => void
  onSelectMask: (mask: Mask) => void
  onResetMoves: () => void
  onToggleBefore: () => void
  onDrawFinal: () => void
  onRedraw: (choice: RedrawChoice) => void
  onUseVersion: (revision: number) => void
  onUseNew: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = dialog.current
    if (!d) return
    if (typeof d.showModal === 'function' && !d.open) d.showModal()
    else d.setAttribute('open', '')
    return () => (typeof d.close === 'function' ? d.close() : d.removeAttribute('open'))
  }, [])

  const { shot, selection } = view
  const comparing = view.showBefore && view.beforeSrc
  return (
    <dialog
      ref={dialog}
      aria-labelledby="editor-title"
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      className="m-auto h-dvh max-h-none w-full max-w-none bg-paper p-0 text-ink backdrop:bg-ink/60 md:h-[min(92dvh,900px)] md:w-[min(96vw,1280px)] md:rounded-md md:border-2 md:border-ink"
      data-testid="panel-editor"
    >
      <div className="flex h-full flex-col">
        <header className="flex items-center justify-between gap-3 border-b-[1.5px] border-rule px-4 py-3">
          <div className="min-w-0">
            <h2 id="editor-title" className="m-0 text-lg font-extrabold wide">
              Shot {shotLabel(shot.number)} <span className="font-semibold text-muted tabular">· revision {view.revision}</span>
            </h2>
            <p className="m-0 truncate text-sm text-muted">
              {framingLabel(shot.framing)} · {seconds(shot.duration_ms)} · {shot.action}
            </p>
          </div>
          <Button onClick={onClose}>Close</Button>
        </header>
        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto p-4 md:grid-cols-[1fr_340px]">
          <div className="flex min-w-0 flex-col gap-3">
            <div className="relative">
              {comparing ? (
                <img src={view.beforeSrc ?? undefined} alt={`Shot ${shot.number}, revision ${view.before?.revision} (before)`} className="frame block w-full" />
              ) : (
                canvas
              )}
              {view.drawing ? (
                <DrawingOverlay label={DRAWING[view.drawing]} />
              ) : (
                (view.selecting || view.preparing) && (
                  <p className="absolute top-3 left-3 m-0 rounded-full bg-ink px-3 py-1 text-sm font-semibold text-paper" role="status">
                    {view.selecting ? 'Finding the object…' : 'Preparing the background…'}
                  </p>
                )
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
              {view.before && view.before.revision !== view.revision && (
                <Button size="sm" aria-pressed={view.showBefore} onClick={onToggleBefore}>
                  {view.showBefore ? `Showing before (revision ${view.before.revision})` : `Compare with revision ${view.before.revision}`}
                </Button>
              )}
              <span>Click a character or object to select it. Drag it to move, pull a corner to resize.</span>
            </div>
          </div>

          <div className="flex flex-col gap-5">
            <section aria-labelledby="sel-title" className="flex flex-col gap-2">
              <h3 id="sel-title" className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
                Selection
              </h3>
              <p className="m-0" role="status" data-testid="selection-status" data-selected={selection ? true : undefined}>
                {selection ? (
                  <>
                    <strong>{selection.mask.label}</strong>{' '}
                    <span className="text-sm text-muted">{selection.cached ? '· ready instantly' : `· found in ${seconds(selection.ms)}`}</span>
                  </>
                ) : (
                  <span className="text-muted">Nothing selected.</span>
                )}
              </p>
              {view.selectError && <Notice tone="warn" title={view.selectError} />}
              {view.masks.length > 0 && (
                <div className="flex flex-wrap gap-2" aria-label="Objects found in this panel">
                  {view.masks.map((m) => (
                    <Button key={m.id} size="sm" aria-pressed={selection?.mask.id === m.id} onClick={() => onSelectMask(m)} className="aria-pressed:bg-ink aria-pressed:text-paper">
                      {m.label}
                    </Button>
                  ))}
                </div>
              )}
              {view.hasMoves && (
                <div className="flex items-center justify-between gap-2 text-sm text-muted">
                  <span>{view.preparing ? 'Saving to the storyboard…' : 'Moves are saved to the storyboard.'}</span>
                  <Button size="sm" variant="quiet" onClick={onResetMoves}>
                    Put everything back
                  </Button>
                </div>
              )}
            </section>

            {editBox}
            {view.editError && <Notice tone="error" title={view.editError} />}
            {view.failed && <Notice tone="error" title={view.failed} />}

            {(view.versions?.length ?? 0) > 0 && (
              <section aria-labelledby="versions-title" className="flex flex-col gap-2" data-testid="versions">
                <h3 id="versions-title" className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
                  Earlier drawings
                </h3>
                {(view.redrawnFrom ?? null) !== null && (
                  <div className="flex flex-wrap items-center gap-2 rounded-md border-[1.5px] border-ink bg-sheet p-2 text-sm" role="group" aria-label="New drawing">
                    <span className="font-semibold">Here’s the new drawing. Keep it?</span>
                    <Button size="sm" variant="ink" disabled={(view.restoring ?? null) !== null} onClick={onUseNew}>
                      Use new
                    </Button>
                    <Button size="sm" disabled={(view.restoring ?? null) !== null} onClick={() => onUseVersion(view.redrawnFrom as number)}>
                      Keep previous
                    </Button>
                  </div>
                )}
                <ul className="m-0 flex list-none gap-2 overflow-x-auto p-0">
                  {view.versions?.map((v) => (
                    <li key={v.revision} className="flex w-28 shrink-0 flex-col gap-1">
                      <img src={v.src} alt={`Shot ${shot.number}, revision ${v.revision}`} className="frame aspect-video w-full object-cover" />
                      <Button size="sm" variant="quiet" className="px-1" disabled={!!view.drawing || (view.restoring ?? null) !== null} onClick={() => onUseVersion(v.revision)} aria-label={`Use revision ${v.revision} again`}>
                        {view.restoring === v.revision ? 'Bringing back…' : 'Use this'}
                      </Button>
                    </li>
                  ))}
                </ul>
                {view.restoreError && <Notice tone="error" title={view.restoreError} />}
              </section>
            )}

            <section aria-labelledby="final-title" className="mt-auto flex flex-col gap-2 border-t-[1.5px] border-rule pt-4">
              <h3 id="final-title" className="m-0 font-bold">
                Happy with it?
              </h3>
              <p className="m-0 text-sm text-muted">
                Draw final redraws this panel at high quality, with the same characters. Redraw tries a new take, and you can say what should change. About 20 seconds, $0.01 each.
              </p>
              <div className="flex flex-wrap items-start gap-2">
                <Button variant="outline" onClick={onDrawFinal} disabled={!!view.drawing}>
                  Draw final
                </Button>
                <RedrawControl
                  key={view.suggestion ?? 'redraw'}
                  subject={`shot ${shot.number}`}
                  className="min-h-11"
                  disabled={!!view.drawing}
                  initialChange={view.suggestion ?? ''}
                  initiallyOpen={!!view.suggestion}
                  onRedraw={onRedraw}
                />
              </div>
            </section>
          </div>
        </div>
      </div>
    </dialog>
  )
}
