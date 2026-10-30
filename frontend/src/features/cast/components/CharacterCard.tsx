import { useId, useRef, useState, type ReactNode } from 'react'
import type { Character } from '../../../shared/api/types'
import { Button } from '../../../shared/ui/Button'
import { Suggestion } from './Suggestion'

export function CharacterCard({
  character,
  imageSrc,
  description,
  redrawing,
  locked,
  others = [],
  busy = false,
  onDescribe,
  onRegenerate,
  onRedrawWith,
  onUseSuggestion,
  onRename,
  onRemove,
  onMerge,
  badge,
  review,
  looks,
}: {
  character: Character
  imageSrc: string | null
  description: string
  redrawing: boolean
  locked: boolean
  /** The rest of the cast, to merge this character into. */
  others?: Character[]
  busy?: boolean
  onDescribe: (text: string) => void
  onRegenerate: () => void
  /** After a failed sheet: draw it with the edited description. */
  onRedrawWith?: () => void
  /** After two refusals: draw it with the suggested description (ADR 0019). */
  onUseSuggestion?: (text: string) => void
  onRename?: (name: string) => void
  onRemove?: () => void
  onMerge?: (into: string) => void
  /** On the sheet: the continuity supervisor's badge. */
  badge?: ReactNode
  /** Under the sheet: the rubric issues to look at before approving. */
  review?: ReactNode
  /** The character's other outfits, each with its sheet (ADR 0018). */
  looks?: ReactNode
}) {
  const id = useId()
  const [mode, setMode] = useState<'view' | 'rename' | 'remove' | 'merge'>('view')
  const [name, setName] = useState(character.name)
  const [into, setInto] = useState('')
  const changed = description.trim() !== character.description
  const done = () => setMode('view')
  const describe = useRef<HTMLTextAreaElement>(null)
  // The sheet could not be drawn (e.g. Muse Image's safety filter): say why, and how to go on.
  const failed = !imageSrc && !redrawing && !!character.sheet_error
  // Refused twice: the same Try again would be refused too, so offer a plainer description instead.
  const suggestion = failed && !changed ? character.suggested_description : null
  return (
    <li className="arrive flex w-64 shrink-0 flex-col gap-2 rounded-md border-[1.5px] border-rule bg-sheet p-3" data-testid="character-card">
      <div className="frame aspect-square">
        {imageSrc && !redrawing ? (
          <>
            <img src={imageSrc} alt={`Reference sheet for ${character.name}`} className="size-full object-cover" />
            {badge}
          </>
        ) : failed ? (
          <div className="flex size-full flex-col items-center justify-center gap-2 p-4 text-center text-sm" role="alert" data-testid="sheet-failed">
            <p className="m-0 font-bold text-danger">{character.name}’s sheet couldn’t be drawn.</p>
            <p className="m-0 text-muted">{character.sheet_error}</p>
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
          <div className="grid size-full place-items-center p-4 text-center text-sm font-semibold text-muted" aria-live="polite">
            {redrawing ? `Redrawing ${character.name}…` : `Drawing ${character.name}’s sheet…`}
          </div>
        )}
      </div>
      {!redrawing && review}
      {(character.looks?.length ?? 0) > 0 && <p className="m-0 -mb-1 text-xs font-bold uppercase tracking-wider text-muted">Everyday</p>}
      {mode === 'rename' ? (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (name.trim() && name.trim() !== character.name) onRename?.(name)
            done()
          }}
        >
          <label htmlFor={`${id}-name`} className="sr-only">
            New name for {character.name}
          </label>
          <input
            id={`${id}-name`}
            value={name}
            maxLength={60}
            autoFocus
            onChange={(e) => setName(e.target.value)}
            className="min-w-0 flex-1 rounded border-[1.5px] border-ink bg-paper px-2 py-1 text-sm font-bold"
          />
          <Button size="sm" type="submit" variant="ink" disabled={!name.trim()}>
            Save
          </Button>
        </form>
      ) : (
        <h3 className="m-0 text-base font-extrabold wide">{character.name}</h3>
      )}
      <label htmlFor={id} className="sr-only">
        Description of {character.name}
      </label>
      <textarea
        ref={describe}
        id={id}
        rows={4}
        value={description}
        readOnly={locked}
        maxLength={600}
        onChange={(e) => onDescribe(e.target.value)}
        className="resize-y rounded border-[1.5px] border-rule bg-paper px-2 py-1.5 text-sm leading-snug read-only:border-transparent read-only:bg-transparent focus:border-ink"
      />
      {changed && !locked && !failed && <p className="m-0 text-xs text-muted">Approving redraws this sheet with your description first.</p>}
      {!locked && !failed && (
        <Button size="sm" onClick={onRegenerate} disabled={redrawing}>
          Regenerate
        </Button>
      )}
      {looks}
      {mode === 'remove' && (
        <div className="flex flex-col gap-2 rounded border-[1.5px] border-danger p-2 text-sm" role="group" aria-label={`Remove ${character.name}`}>
          <p className="m-0">Remove {character.name}? Their shots keep their action, without them.</p>
          <div className="flex gap-2">
            <Button size="sm" variant="ink" disabled={busy} onClick={() => (onRemove?.(), done())}>
              Remove {character.name}
            </Button>
            <Button size="sm" variant="quiet" onClick={done}>
              Keep
            </Button>
          </div>
        </div>
      )}
      {mode === 'merge' && (
        <form
          className="flex flex-col gap-2 rounded border-[1.5px] border-rule p-2 text-sm"
          onSubmit={(e) => {
            e.preventDefault()
            if (into) onMerge?.(into)
            done()
          }}
        >
          <label htmlFor={`${id}-into`}>{character.name} is really…</label>
          <select id={`${id}-into`} value={into} onChange={(e) => setInto(e.target.value)} className="rounded border-[1.5px] border-ink bg-paper px-2 py-1">
            <option value="">Choose a character</option>
            {others.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
          <p className="m-0 text-xs text-muted">Their shots show that character instead and are drawn again as drafts.</p>
          <div className="flex gap-2">
            <Button size="sm" type="submit" variant="ink" disabled={!into || busy}>
              Merge
            </Button>
            <Button size="sm" variant="quiet" onClick={done}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {mode === 'view' && (onRename || onRemove || onMerge) && (
        <div className="flex flex-wrap gap-1" aria-label={`Change ${character.name}`}>
          {onRename && (
            <Button size="sm" variant="quiet" disabled={busy} onClick={() => (setName(character.name), setMode('rename'))}>
              Rename
            </Button>
          )}
          {onMerge && others.length > 0 && (
            <Button size="sm" variant="quiet" disabled={busy} onClick={() => (setInto(''), setMode('merge'))}>
              Merge into…
            </Button>
          )}
          {onRemove && (
            <Button size="sm" variant="quiet" disabled={busy} onClick={() => setMode('remove')}>
              Remove
            </Button>
          )}
        </div>
      )}
    </li>
  )
}
