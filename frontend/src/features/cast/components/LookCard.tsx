import { useId, useRef } from 'react'
import type { Look } from '../../../shared/api/types'
import { Button } from '../../../shared/ui/Button'
import { Suggestion } from './Suggestion'

/** "Shots 2–6", "Shot 4", or nothing when no shot shows the look yet. */
export function shotsLabel(numbers: number[]): string {
  if (numbers.length === 0) return ''
  const contiguous = numbers.every((n, i) => i === 0 || n === (numbers[i - 1] ?? 0) + 1)
  if (numbers.length === 1) return `Shot ${numbers.join('')}`
  return contiguous ? `Shots ${numbers[0]}–${numbers.at(-1)}` : `Shots ${numbers.join(', ')}`
}

/** One of a character's outfits (ADR 0018): its sheet, which shots wear it, and its clothes to edit. */
export function LookCard({
  look,
  name,
  imageSrc,
  clothes,
  redrawing,
  locked,
  onDescribe,
  onRegenerate,
  onRedrawWith,
  onUseSuggestion,
}: {
  look: Look
  /** The character's name. */
  name: string
  imageSrc: string | null
  /** The clothes as the user is editing them. */
  clothes: string
  redrawing: boolean
  locked: boolean
  onDescribe: (text: string) => void
  onRegenerate: () => void
  onRedrawWith: () => void
  /** After two refusals: draw it with the suggested clothes (ADR 0019). */
  onUseSuggestion?: (text: string) => void
}) {
  const id = useId()
  const describe = useRef<HTMLTextAreaElement>(null)
  const changed = clothes.trim() !== look.clothes
  const failed = !imageSrc && !redrawing && !!look.sheet_error
  const suggestion = failed && !changed ? look.suggested_clothes : null
  const shots = shotsLabel(look.from_shots)
  return (
    <div className="flex flex-col gap-2 border-t-[1.5px] border-rule pt-2" data-testid="look-card" aria-label={`${name}: ${look.label}`} role="group">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="m-0 text-sm font-extrabold">{look.label}</h4>
        {shots && <span className="text-xs text-muted">{shots}</span>}
      </div>
      <div className="frame aspect-square">
        {imageSrc && !redrawing ? (
          <img src={imageSrc} alt={`Reference sheet for ${name}, ${look.label.toLowerCase()}`} className="size-full object-cover" />
        ) : failed ? (
          <div className="flex size-full flex-col items-center justify-center gap-2 p-3 text-center text-sm" role="alert">
            <p className="m-0 font-bold text-danger">This look couldn’t be drawn.</p>
            <p className="m-0 text-muted">{look.sheet_error}</p>
            {suggestion && <Suggestion text={suggestion} />}
            <div className="flex flex-wrap justify-center gap-2">
              {suggestion ? (
                <Button size="sm" variant="ink" onClick={() => onUseSuggestion?.(suggestion)}>
                  Use this description
                </Button>
              ) : (
                <Button size="sm" variant="ink" onClick={changed ? onRedrawWith : onRegenerate}>
                  {changed ? 'Draw with this description' : 'Try again'}
                </Button>
              )}
              <Button size="sm" onClick={() => describe.current?.focus()}>
                Edit description
              </Button>
            </div>
          </div>
        ) : (
          <div className="grid size-full place-items-center p-3 text-center text-sm font-semibold text-muted" aria-live="polite">
            {redrawing ? `Redrawing ${name}’s ${look.label.toLowerCase()}…` : `Drawing ${name}’s ${look.label.toLowerCase()}…`}
          </div>
        )}
      </div>
      <label htmlFor={id} className="sr-only">
        What {name} wears: {look.label}
      </label>
      <textarea
        ref={describe}
        id={id}
        rows={3}
        value={clothes}
        readOnly={locked}
        maxLength={400}
        onChange={(e) => onDescribe(e.target.value)}
        className="resize-y rounded border-[1.5px] border-rule bg-paper px-2 py-1.5 text-sm leading-snug read-only:border-transparent read-only:bg-transparent focus:border-ink"
      />
      {changed && !locked && !failed && <p className="m-0 text-xs text-muted">Approving redraws this look with your description first.</p>}
      {!locked && !failed && (
        <Button size="sm" onClick={onRegenerate} disabled={redrawing}>
          Try again
        </Button>
      )}
    </div>
  )
}
