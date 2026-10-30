import type { Turn } from '../../../shared/api/types'
import { TurnCard } from './TurnCard'

/** Beats of the same recording and episode can be merged; live turn ids start with their session tag. */
function mergeable(a: Turn | undefined, b: Turn | undefined): boolean {
  return !!a && !!b && a.id.split('-')[0] === b.id.split('-')[0] && a.episode === b.episode
}

export function TranscriptRail({
  turns,
  partial,
  listening,
  correcting,
  onCorrect,
  onRemove,
  onMerge,
}: {
  turns: Turn[]
  partial: string
  listening: boolean
  correcting: Record<string, 'sending' | 'failed'>
  onCorrect: (turnId: string, text: string) => void
  /** Remove a beat; `index` is its place, for "Beat 2 removed". Not offered while listening. */
  onRemove?: (turnId: string, index: number) => void
  onMerge?: (turnId: string, other: 'previous' | 'next') => void
}) {
  return (
    <section aria-labelledby="transcript-title" className="flex min-h-0 flex-col gap-3">
      <h2 id="transcript-title" className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
        Transcript
      </h2>
      {turns.length === 0 && !partial && (
        <p className="m-0 text-sm text-muted">
          {listening ? 'Start talking. Your words appear here.' : 'Say the scene out loud. Each beat you cut becomes a card here, and you can fix any misheard word.'}
        </p>
      )}
      <ol className="m-0 flex list-none flex-col gap-2 p-0">
        {turns.map((t, i) => (
          <TurnCard
            key={t.id}
            turn={t}
            index={i}
            status={correcting[t.id]}
            onCorrect={onCorrect}
            onRemove={onRemove && !listening ? () => onRemove(t.id, i) : undefined}
            onMerge={onMerge && !listening ? (other) => onMerge(t.id, other) : undefined}
            canMergePrevious={mergeable(turns[i - 1], t)}
            canMergeNext={mergeable(t, turns[i + 1])}
          />
        ))}
      </ol>
      {partial && (
        <p className="m-0 rounded-md border-[1.5px] border-dashed border-blue bg-wash/60 p-3 text-ink" aria-live="polite" data-testid="partial">
          <span className="sr-only">Hearing: </span>
          {partial}
          <span aria-hidden="true" className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-blue align-middle" />
        </p>
      )}
    </section>
  )
}
