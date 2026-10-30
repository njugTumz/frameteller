import { seconds } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'

/**
 * The narrator's recording is kept (with consent) for the animatic. It can be heard here, and one click deletes it.
 * `recordings` are playable urls, one per recording session.
 */
export function RecordingKept({ durationMs, recordings, onDelete }: { durationMs: number; recordings: string[]; onDelete: () => void }) {
  return (
    <div className="space-y-2 rounded-md border-[1.5px] border-rule bg-paper px-3 py-2 text-sm" data-testid="recording-kept">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-muted">Your recording ({seconds(durationMs)}) is kept for the animatic.</span>
        <Button size="sm" variant="quiet" onClick={onDelete}>
          Delete my recording
        </Button>
      </div>
      {recordings.length > 0 && (
        <div className="space-y-1">
          <p className="font-semibold">Listen to your narration</p>
          {recordings.map((src, i) => (
            <audio key={src} src={src} controls preload="none" className="w-full" aria-label={recordings.length > 1 ? `Your narration, part ${i + 1}` : 'Your narration'} />
          ))}
        </div>
      )}
    </div>
  )
}
