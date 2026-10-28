import type { FormEvent, ReactNode } from 'react'
import type { PanelStyle } from '../../../shared/api/types'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
import { CutoutArt, PencilArt, StyleCard } from './StyleCard'

export interface StartForm {
  title: string
  style: PanelStyle
  names: string
}

export function StartScreen({
  form,
  creating,
  error,
  wakeNotice,
  onChange,
  onSubmit,
}: {
  form: StartForm
  creating: boolean
  error: string | null
  wakeNotice: ReactNode
  onChange: (patch: Partial<StartForm>) => void
  onSubmit: () => void
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
      {wakeNotice && <div className="mb-6">{wakeNotice}</div>}
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

        <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
          <legend className="mb-3 text-lg font-bold">How you'll tell it</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex cursor-pointer items-start gap-3 rounded-md border-2 border-ink bg-paper p-3 has-focus-visible:outline-3 has-focus-visible:outline-focus">
              <input type="radio" name="mode" value="narrate" defaultChecked className="mt-1 size-4 accent-[var(--ink)]" />
              <span>
                <span className="block font-bold">Narrate</span>
                <span className="text-sm text-muted">One voice tells the story and cuts the shots.</span>
              </span>
            </label>
            <label className="flex cursor-not-allowed items-start gap-3 rounded-md border-2 border-dashed border-rule p-3 text-muted">
              <input type="radio" name="mode" value="co_direct" disabled aria-describedby="co-direct-soon" className="mt-1 size-4" />
              <span>
                <span className="block font-bold">Co-direct</span>
                <span id="co-direct-soon" className="text-sm">
                  Two voices, labelled A and B. Coming soon.
                </span>
              </span>
            </label>
          </div>
        </fieldset>

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

        {error && <Notice tone="error" title={error} />}

        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" variant="marker" size="lg" disabled={creating} className="font-extrabold wide">
            {creating ? 'Setting up the desk…' : 'Open the studio'}
          </Button>
          <span className="text-sm text-muted">You'll allow the microphone next.</span>
        </div>
      </form>
    </div>
  )
}
