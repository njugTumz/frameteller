import { Button } from '../../../shared/ui/Button'
import type { PendingRemoval } from '../store'

/** "Beat 2 removed. Undo" at the bottom of the screen, for 10 seconds. No confirm dialog: Undo is the safety net. */
export function UndoToast({ pending, onUndo }: { pending: PendingRemoval | null; onUndo: () => void }) {
  if (!pending) return null
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="undo-toast"
      className="fixed inset-x-4 bottom-4 z-40 mx-auto flex max-w-md items-center justify-between gap-3 rounded-md bg-ink px-4 py-3 text-paper shadow-lg"
    >
      <span className="text-sm font-semibold">
        {pending.label} removed.
        {pending.kind === 'beat' && <span className="font-normal"> Its words and voice leave the animatic.</span>}
      </span>
      <Button size="sm" variant="outline" className="shrink-0 bg-paper text-ink" onClick={onUndo}>
        Undo
      </Button>
    </div>
  )
}
