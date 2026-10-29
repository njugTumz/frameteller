import { useRef, useState, type ChangeEvent } from 'react'
import type { ScriptFormat } from '../../../shared/events'
import { Button } from '../../../shared/ui/Button'
import { MAX_SCRIPT_CHARS, SCRIPT_TYPES, readScriptFile, scriptFormat } from '../choice'

/** Paste a script or upload a .txt, .md or .fountain file. Each paragraph becomes one shot. */
export function ScriptInput({
  text,
  onChange,
}: {
  text: string
  onChange: (text: string, format: ScriptFormat) => void
}) {
  const file = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const over = text.length > MAX_SCRIPT_CHARS

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const chosen = e.target.files?.[0]
    e.target.value = '' // the same file can be chosen again
    if (!chosen) return
    try {
      const read = await readScriptFile(chosen)
      setError(null)
      onChange(read.text, read.format)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That file could not be read.')
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <label htmlFor="script-text" className="text-lg font-bold">
          Your script
        </label>
        <Button size="sm" onClick={() => file.current?.click()}>
          Upload .txt, .md or .fountain
        </Button>
        <input ref={file} type="file" accept={SCRIPT_TYPES} className="sr-only" tabIndex={-1} aria-label="Upload a script file" onChange={(e) => void upload(e)} />
      </div>
      <textarea
        id="script-text"
        value={text}
        rows={9}
        placeholder={'Wide shot. Night over the rooftops. Lena feeds the pigeons.\n\nA paper kite drifts down into her hands.\n\nEpisode 2\n\n…'}
        aria-describedby="script-help script-count"
        onChange={(e) => onChange(e.target.value, scriptFormat(e.target.value))}
        className="rounded border-2 border-ink bg-paper px-3 py-2.5 font-[inherit] leading-relaxed"
      />
      <div className="flex flex-wrap justify-between gap-2 text-sm">
        <p id="script-help" className="m-0 text-muted">
          Each paragraph becomes a shot. Cues like “Wide shot.” guide the camera. A line “Episode 2” starts the next episode, up to 3.
        </p>
        <span id="script-count" className={over ? 'font-bold text-danger tabular' : 'text-muted tabular'} aria-live="polite">
          {text.length.toLocaleString('en-US')} / {MAX_SCRIPT_CHARS.toLocaleString('en-US')}
        </span>
      </div>
      {error && (
        <p role="alert" className="m-0 text-sm font-semibold text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
