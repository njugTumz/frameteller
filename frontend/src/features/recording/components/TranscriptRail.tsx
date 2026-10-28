import type { Turn } from '../../../shared/api/types'
import { TurnCard } from './TurnCard'

export function TranscriptRail({
  turns,
  partial,
  listening,
  correcting,
  onCorrect,
}: {
  turns: Turn[]
  partial: string
  listening: boolean
  correcting: Record<string, 'sending' | 'failed'>
  onCorrect: (turnId: string, text: string) => void
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
          <TurnCard key={t.id} turn={t} index={i} status={correcting[t.id]} onCorrect={onCorrect} />
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
