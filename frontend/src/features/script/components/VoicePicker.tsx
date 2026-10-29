import type { Voice } from '../../../shared/api/types'
import { Button } from '../../../shared/ui/Button'

/** "Read it to me": pick a voice (each with a preview) and a language it speaks. */
export function VoicePicker({
  voices,
  voice,
  language,
  previewing = null,
  onChange,
  onPreview,
}: {
  voices: Voice[]
  voice: string
  language: string
  /** The voice whose preview is playing. */
  previewing?: string | null
  onChange: (voice: string, language: string) => void
  onPreview: (voice: Voice, language: string) => void
}) {
  const chosen = voices.find((v) => v.name === voice) ?? voices[0]
  const preview = (v: Voice) => {
    const locale = v.languages.some((l) => l.locale === language) ? language : (v.languages[0]?.locale ?? 'en-US')
    onPreview(v, locale)
  }

  const pick = (v: Voice) => {
    // Keep the language if the new voice speaks it; English (in its own accent) otherwise.
    const code = chosen?.languages.find((l) => l.locale === language)?.code ?? 'en'
    const kept = v.languages.find((l) => l.code === code) ?? v.languages[0]
    onChange(v.name, kept?.locale ?? language)
  }

  return (
    <div className="flex flex-col gap-4">
      <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
        <legend className="mb-2 text-lg font-bold">Pick a voice</legend>
        <ul className="m-0 grid list-none gap-2 p-0 sm:grid-cols-2">
          {voices.map((v) => (
            <li key={v.name} className="flex items-center justify-between gap-2 rounded-md border-2 border-ink bg-paper p-2.5 has-checked:bg-wash">
              <label className="flex cursor-pointer items-center gap-2.5">
                <input type="radio" name="voice" value={v.name} checked={chosen?.name === v.name} onChange={() => pick(v)} className="size-4 accent-[var(--ink)]" />
                <span>
                  <span className="block font-bold">{v.display_name}</span>
                  <span className="text-sm text-muted">
                    {v.gender === 'Female' ? 'Female' : 'Male'}, {v.accent === 'en-GB' ? 'UK' : 'US'}
                  </span>
                </span>
              </label>
              <Button size="sm" variant="quiet" aria-label={`Hear ${v.display_name}`} onClick={() => preview(v)} disabled={previewing === v.name}>
                {previewing === v.name ? 'Playing…' : 'Preview'}
              </Button>
            </li>
          ))}
        </ul>
      </fieldset>
      {chosen && (
        <div className="flex flex-col gap-2">
          <label htmlFor="voice-language" className="font-bold">
            Language
          </label>
          <select
            id="voice-language"
            value={language}
            onChange={(e) => onChange(chosen.name, e.target.value)}
            aria-describedby="language-help"
            className="rounded border-2 border-ink bg-paper px-3 py-2"
          >
            {chosen.languages.map((l) => (
              <option key={l.locale} value={l.locale}>
                {l.name}
              </option>
            ))}
          </select>
          <p id="language-help" className="m-0 text-sm text-muted">
            For another language, the script is translated before it's read. The panels follow your original words.
          </p>
        </div>
      )}
    </div>
  )
}
