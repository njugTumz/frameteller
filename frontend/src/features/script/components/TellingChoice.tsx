import type { TellingMode } from '../store'

const CHOICES: { mode: TellingMode; title: string; note: string }[] = [
  { mode: 'narrate', title: 'Narrate', note: 'Make it up out loud. Press Space for each shot.' },
  { mode: 'teleprompter', title: 'Teleprompter', note: 'Paste a script and read it aloud as it scrolls. Each paragraph becomes a shot.' },
  { mode: 'read', title: 'Read it to me', note: 'Paste a script, pick a voice and a language, and listen while it draws.' },
]

/** "How you'll tell it": the three ways to tell a story (ADR 0015). */
export function TellingChoice({
  mode,
  readAvailable,
  onChange,
}: {
  mode: TellingMode
  /** False when the studio has no Text-to-Speech: "Read it to me" is shown but cannot be picked. */
  readAvailable: boolean
  onChange: (mode: TellingMode) => void
}) {
  return (
    <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
      <legend className="mb-3 text-lg font-bold">How you'll tell it</legend>
      <div className="grid gap-3 sm:grid-cols-3">
        {CHOICES.map((c) => {
          const disabled = c.mode === 'read' && !readAvailable
          return (
            <label
              key={c.mode}
              className={
                disabled
                  ? 'flex cursor-not-allowed items-start gap-3 rounded-md border-2 border-dashed border-rule p-3 text-muted'
                  : 'flex cursor-pointer items-start gap-3 rounded-md border-2 border-ink bg-paper p-3 has-checked:bg-wash has-focus-visible:outline-3 has-focus-visible:outline-focus'
              }
            >
              <input
                type="radio"
                name="mode"
                value={c.mode}
                checked={mode === c.mode}
                disabled={disabled}
                onChange={() => onChange(c.mode)}
                className="mt-1 size-4 accent-[var(--ink)]"
              />
              <span>
                <span className="block font-bold">{c.title}</span>
                <span className="text-sm text-muted">{disabled ? 'Not available right now.' : c.note}</span>
              </span>
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
