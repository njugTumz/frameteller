import { useState } from 'react'
import { Button } from '../../../shared/ui/Button'
import { cx } from '../../../shared/ui/cx'

/** "Next shot": the narrator's beat (ADR 0008). Space does the same while telling; on touch screens it is a big button with no key hint. */
export function BeatButton({ enabled, beats, onBeat }: { enabled: boolean; beats: number; onBeat: () => void }) {
  const [pressed, setPressed] = useState(0)
  return (
    <div className="flex flex-col items-stretch gap-1.5">
      <Button
        variant="marker"
        size="lg"
        disabled={!enabled}
        aria-keyshortcuts="Space"
        aria-describedby="beat-help"
        className={cx('w-full text-xl font-extrabold wide pointer-coarse:min-h-18', pressed > 0 && 'pressed')}
        key={pressed}
        onClick={() => {
          onBeat()
          setPressed((n) => n + 1)
        }}
      >
        Next shot
        <kbd className="rounded border-[1.5px] border-current px-1.5 py-0.5 text-xs font-semibold pointer-coarse:hidden">Space</kbd>
      </Button>
      <p id="beat-help" className="m-0 text-center text-sm text-muted tabular" aria-live="polite">
        {enabled ? (beats === 0 ? 'Press it in the pause before each new shot.' : `${beats} ${beats === 1 ? 'cut' : 'cuts'} so far`) : 'Start telling to cut shots.'}
      </p>
    </div>
  )
}
