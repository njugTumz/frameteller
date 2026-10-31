import type { FormEvent, ReactNode } from 'react'
import type { PanelStyle } from '../../../shared/api/types'
import { Button } from '../../../shared/ui/Button'
import { STUDIO_FULL } from '../../../shared/status/store'
import { Notice } from '../../../shared/ui/Notice'
import type { ScriptFormat } from '../../../shared/events'
import type { Voice, Voices } from '../../../shared/api/types'
import { ScriptInput } from '../../script/components/ScriptInput'
import { TellingChoice } from '../../script/components/TellingChoice'
import { VoicePicker } from '../../script/components/VoicePicker'
import type { TellingMode } from '../../script/store'
import { LANGUAGES } from '../../../shared/languages'
import { CutoutArt, PencilArt, StyleCard } from './StyleCard'

export interface StartForm {
  title: string
  style: PanelStyle
  names: string
  keepAudio: boolean
  mode: TellingMode
  script: string
  format: ScriptFormat
  voice: string
  language: string
  speaking: string
}

const NO_VOICES: Voices = { available: false, default: '', voices: [] }

export function StartScreen({
  form,
  creating,
  error,
  full = false,
  voices = NO_VOICES,
  previewing = null,
  onPreview = () => undefined,
  wakeNotice,
  onChange,
  onSubmit,
  onSample,
  guide = null,
}: {
  form: StartForm
  creating: boolean
  error: string | null
  /** The day's global spend cap is reached: no new stories until tomorrow. */
  full?: boolean
  /** The voices "Read it to me" offers (GET /voices). */
  voices?: Voices
  previewing?: string | null
  onPreview?: (voice: Voice, language: string) => void
  wakeNotice: ReactNode
  onChange: (patch: Partial<StartForm>) => void
  onSubmit: () => void
  /** "Try a sample story": the built-in script, read aloud, for visitors without a microphone. */
  onSample?: () => void
  /** The first-visit guide, when this browser has not dismissed it. */
  guide?: ReactNode
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 md:py-16">
      <h1 className="m-0 text-5xl leading-[0.95] font-black tracking-tight widest md:text-7xl">
        Say the scene.
        <span className="block text-blue">See the storyboard.</span>
      </h1>
      <p className="mt-5 mb-8 max-w-[58ch] text-lg text-muted">
        Tell your story out loud. Press <strong className="text-ink">Next shot</strong> in the pause before each new shot, and the panels draw themselves, with the same characters in every frame.
      </p>
      {full && (
        <Notice tone="warn" title={STUDIO_FULL} className="mb-6">
          So many stories were told today that the public demo has used its budget. Shared storyboards still open.
        </Notice>
      )}
      {wakeNotice && <div className="mb-6">{wakeNotice}</div>}
      {guide}
      {onSample && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-md border-[1.5px] border-dashed border-rule p-4">
          <p className="m-0 flex-1 basis-60 text-sm">
            <strong>No microphone, or just curious?</strong> Watch a short story about a girl and a rooftop robot become a storyboard, read aloud by a voice.
          </p>
          <Button onClick={onSample} disabled={creating || full}>
            Try a sample story
          </Button>
        </div>
      )}
      <form onSubmit={submit} className="flex flex-col gap-8 rounded-md border-[1.5px] border-rule bg-sheet p-5 md:p-8">
        <div className="flex flex-col gap-2">
          <label htmlFor="story-title" className="text-lg font-bold">
            Name the story
          </label>
          <input
            id="story-title"
            value={form.title}
            maxLength={120}
            placeholder="The Lantern Cat"
            autoComplete="off"
            onChange={(e) => onChange({ title: e.target.value })}
            className="rounded border-2 border-ink bg-paper px-3 py-2.5 text-lg"
          />
        </div>

        <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
          <legend className="mb-3 text-lg font-bold">Pick a style</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            <StyleCard value="pencil" checked={form.style === 'pencil'} title="Pencil storyboard" note="Clean sketch lines, one accent colour. Reads like a real storyboard." art={<PencilArt />} onSelect={() => onChange({ style: 'pencil' })} />
            <StyleCard value="paper_cutout" checked={form.style === 'paper_cutout'} title="Paper cutout" note="Layered coloured paper with soft shadows. Good for children's stories." art={<CutoutArt />} onSelect={() => onChange({ style: 'paper_cutout' })} />
          </div>
        </fieldset>

        <TellingChoice mode={form.mode} readAvailable={voices.available} onChange={(mode) => onChange({ mode })} />

        {form.mode !== 'narrate' && <ScriptInput text={form.script} onChange={(script, format) => onChange({ script, format })} />}

        {form.mode === 'read' && voices.available && (
          <VoicePicker
            voices={voices.voices}
            voice={form.voice}
            language={form.language}
            previewing={previewing}
            onChange={(voice, language) => onChange({ voice, language })}
            onPreview={onPreview}
          />
        )}

        {form.mode !== 'read' && (
          <div className="flex flex-col gap-2">
            <label htmlFor="speaking-language" className="font-bold">
              Language you'll speak
            </label>
            <select
              id="speaking-language"
              value={form.speaking}
              aria-describedby="speaking-help"
              onChange={(e) => onChange({ speaking: e.target.value })}
              className="w-fit rounded border-2 border-ink bg-paper px-3 py-2"
            >
              <option value="">Detect automatically</option>
              {LANGUAGES.map((l) => (
                <option key={l.locale} value={l.locale} lang={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
            <p id="speaking-help" className="m-0 text-sm text-muted">
              Choosing it helps the transcript, and the captions come out in the same language.
            </p>
          </div>
        )}

        {form.mode !== 'read' && (
        <div className="flex flex-col gap-2">
          <label htmlFor="story-names" className="font-bold">
            Names in the story <span className="font-normal text-muted">(optional)</span>
          </label>
          <input
            id="story-names"
            value={form.names}
            placeholder="Mira, Lantern Lane"
            autoComplete="off"
            aria-describedby="names-help"
            onChange={(e) => onChange({ names: e.target.value })}
            className="rounded border-2 border-ink bg-paper px-3 py-2"
          />
          <p id="names-help" className="m-0 text-sm text-muted">
            Separate them with commas. They help the transcriber spell your characters and places right.
          </p>
        </div>
        )}

        {form.mode !== 'read' && (
        <div className="flex items-start gap-3">
          <input
            id="keep-audio"
            type="checkbox"
            checked={form.keepAudio}
            aria-describedby="keep-audio-help"
            onChange={(e) => onChange({ keepAudio: e.target.checked })}
            className="mt-1 size-5 accent-[var(--ink)]"
          />
          <div>
            <label htmlFor="keep-audio" className="choice font-bold">
              Keep my narration for the animatic
            </label>
            <p id="keep-audio-help" className="m-0 text-sm text-muted">
              Your recording becomes the animatic's voice track. It stays with this story, and you can delete it any time.
            </p>
          </div>
        </div>
        )}

        {error && <Notice tone="error" title={error} />}

        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" variant="marker" size="lg" disabled={creating || full} className="font-extrabold wide">
            {creating ? 'Setting up the desk…' : 'Open the studio'}
          </Button>
          <span className="text-sm text-muted">
            {form.mode === 'read' ? 'The voice reads in the studio, so turn your sound on.' : "You'll allow the microphone next."}{' '}
            <a href="/privacy">What we keep, and for how long</a>
          </span>
        </div>
      </form>
    </div>
  )
}
