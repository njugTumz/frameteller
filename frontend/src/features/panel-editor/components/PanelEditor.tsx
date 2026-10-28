import { useEffect, useRef, type ReactNode } from 'react'
import type { Mask, Shot } from '../../../shared/api/types'
import { framingLabel, seconds, shotLabel } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
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
}

const DRAWING = { draft: 'Drawing draft…', final: 'Drawing the final panel…', change: 'Making your change…' } as const

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
}: {
  view: EditorView
  canvas: ReactNode
  editBox: ReactNode
  onClose: () => void
  onSelectMask: (mask: Mask) => void
  onResetMoves: () => void
  onToggleBefore: () => void
  onDrawFinal: () => void
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
              {(view.drawing || view.selecting) && (
                <p className="absolute top-3 left-3 m-0 rounded-full bg-ink px-3 py-1 text-sm font-semibold text-paper" role="status">
                  {view.drawing ? DRAWING[view.drawing] : 'Finding the object…'}
                </p>
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
              <p className="m-0" role="status" data-testid="selection-status">
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
                  <span>Moves and resizes are kept on this device.</span>
                  <Button size="sm" variant="quiet" onClick={onResetMoves}>
                    Put everything back
                  </Button>
                </div>
              )}
            </section>

            {editBox}
            {view.editError && <Notice tone="error" title={view.editError} />}
            {view.failed && <Notice tone="error" title={view.failed} />}

            <section aria-labelledby="final-title" className="mt-auto flex flex-col gap-2 border-t-[1.5px] border-rule pt-4">
              <h3 id="final-title" className="m-0 font-bold">
                Happy with it?
              </h3>
              <p className="m-0 text-sm text-muted">Draw final redraws this panel at high quality, with the same characters. About 20 seconds, $0.01.</p>
              <Button variant="outline" onClick={onDrawFinal} disabled={!!view.drawing}>
                Draw final
              </Button>
            </section>
          </div>
        </div>
      </div>
    </dialog>
  )
}
