import { Button } from '../../../shared/ui/Button'
import type { Telling } from '../../recording/store'
import type { Reading } from '../store'

/** "Read it to me": start, pause and continue the voice, and the break between episodes. */
export function ReadingControls({
  telling,
  reading,
  nextEpisode,
  voiceName,
  languageName,
  onStart,
  onPause,
  onContinue,
  onStop,
}: {
  telling: Telling
  reading: Reading
  nextEpisode: number | null
  voiceName: string
  languageName: string
  onStart: () => void
  onPause: () => void
  onContinue: () => void
  onStop: () => void
}) {
  const live = telling === 'live'
  const status =
    telling === 'connecting'
      ? 'Connecting to the studio…'
      : telling === 'finishing'
        ? 'Directing the last shot…'
        : !live
          ? telling === 'ended'
            ? 'Done. Read it again any time.'
            : `${voiceName} will read it in ${languageName}.`
          : reading === 'episode-break'
            ? `Episode ${nextEpisode ?? ''} is next. Drawing this episode's panels first…`
            : reading === 'paused'
              ? 'Paused.'
              : `${voiceName} is reading.`
  return (
    <section aria-label="Reading" className="flex flex-col gap-4 rounded-md border-[1.5px] border-rule bg-sheet p-4">
      <p className="m-0 flex items-center gap-2 font-semibold" role="status">
        <span aria-hidden="true" className={live && reading === 'reading' ? 'live-dot size-2.5 rounded-full bg-marker ring-1 ring-ink' : 'size-2.5 rounded-full bg-rule'} />
        {status}
      </p>
      {!live ? (
        <Button variant="ink" onClick={onStart} disabled={telling === 'connecting' || telling === 'finishing'}>
          {telling === 'ended' ? 'Read it again' : 'Read it to me'}
        </Button>
      ) : (
        <div className="flex flex-wrap gap-2">
          {reading === 'reading' ? (
            <Button variant="ink" onClick={onPause}>
              Pause
            </Button>
          ) : (
            <Button variant="marker" onClick={onContinue} className="font-extrabold">
              {reading === 'episode-break' ? `Start episode ${nextEpisode ?? ''} now` : 'Continue'}
            </Button>
          )}
          <Button onClick={onStop}>Stop</Button>
        </div>
      )}
    </section>
  )
}
