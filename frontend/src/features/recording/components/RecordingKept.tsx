import { seconds } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'

/** The narrator's recording is kept (with consent) for the animatic. One click deletes it. */
export function RecordingKept({ durationMs, onDelete }: { durationMs: number; onDelete: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border-[1.5px] border-rule bg-paper px-3 py-2 text-sm" data-testid="recording-kept">
      <span className="text-muted">Your recording ({seconds(durationMs)}) is kept for the animatic.</span>
      <Button size="sm" variant="quiet" onClick={onDelete}>
        Delete my recording
      </Button>
    </div>
  )
}
