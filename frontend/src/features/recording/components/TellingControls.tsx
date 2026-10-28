import { Button } from '../../../shared/ui/Button'
import type { Telling } from '../store'
import { BeatButton } from './BeatButton'
import { MicMeter } from './MicMeter'

const STATUS: Record<Telling, string> = {
  idle: 'Ready when you are.',
  mic: 'Asking for the microphone…',
  connecting: 'Connecting to the studio…',
  live: 'Listening.',
  finishing: 'Directing the last shot…',
  ended: 'Done. Tell more any time.',
}

export function TellingControls({
  telling,
  level,
  beats,
  onStart,
  onStop,
  onBeat,
}: {
  telling: Telling
  level: number
  beats: number
  onStart: () => void
  onStop: () => void
  onBeat: () => void
}) {
  const live = telling === 'live'
  const busy = telling === 'mic' || telling === 'connecting' || telling === 'finishing'
  return (
    <section aria-label="Telling" className="flex flex-col gap-4 rounded-md border-[1.5px] border-rule bg-sheet p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="m-0 flex items-center gap-2 font-semibold" role="status">
          <span
            aria-hidden="true"
            className={live ? 'live-dot size-2.5 rounded-full bg-marker ring-1 ring-ink' : 'size-2.5 rounded-full bg-rule'}
          />
          {STATUS[telling]}
        </p>
        <MicMeter level={level} active={live} />
      </div>
      {live || telling === 'connecting' ? (
        <Button variant="outline" onClick={onStop} disabled={telling !== 'live'}>
          Stop telling
        </Button>
      ) : (
        <Button variant="ink" onClick={onStart} disabled={busy}>
          {telling === 'ended' ? 'Tell more' : 'Start telling'}
        </Button>
      )}
      <BeatButton enabled={live} beats={beats} onBeat={onBeat} />
    </section>
  )
}
