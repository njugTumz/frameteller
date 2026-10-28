import { useId } from 'react'
import type { Character } from '../../../shared/api/types'
import { Button } from '../../../shared/ui/Button'

export function CharacterCard({
  character,
  imageSrc,
  description,
  redrawing,
  locked,
  onDescribe,
  onRegenerate,
}: {
  character: Character
  imageSrc: string | null
  description: string
  redrawing: boolean
  locked: boolean
  onDescribe: (text: string) => void
  onRegenerate: () => void
}) {
  const id = useId()
  const changed = description.trim() !== character.description
  return (
    <li className="arrive flex w-64 shrink-0 flex-col gap-2 rounded-md border-[1.5px] border-rule bg-sheet p-3" data-testid="character-card">
      <div className="frame aspect-square">
        {imageSrc && !redrawing ? (
          <img src={imageSrc} alt={`Reference sheet for ${character.name}`} className="size-full object-cover" />
        ) : (
          <div className="grid size-full place-items-center p-4 text-center text-sm font-semibold text-muted" aria-live="polite">
            {redrawing ? `Redrawing ${character.name}…` : `Drawing ${character.name}’s sheet…`}
          </div>
        )}
      </div>
      <h3 className="m-0 text-base font-extrabold wide">{character.name}</h3>
      <label htmlFor={id} className="sr-only">
        Description of {character.name}
      </label>
      <textarea
        id={id}
        rows={4}
        value={description}
        readOnly={locked}
        maxLength={600}
        onChange={(e) => onDescribe(e.target.value)}
        className="resize-y rounded border-[1.5px] border-rule bg-paper px-2 py-1.5 text-sm leading-snug read-only:border-transparent read-only:bg-transparent focus:border-ink"
      />
      {changed && !locked && <p className="m-0 text-xs text-muted">Approving redraws this sheet with your description first.</p>}
      {!locked && (
        <Button size="sm" onClick={onRegenerate} disabled={redrawing}>
          Regenerate
        </Button>
      )}
    </li>
  )
}
