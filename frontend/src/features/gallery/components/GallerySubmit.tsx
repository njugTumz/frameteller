import { useId, useState } from 'react'
import type { GalleryAudio, MyGalleryEntry } from '../../../shared/api/types'
import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'

export const CONSENT =
  'I made this story, it has no real people or characters from films, shows, games or brands, and I agree to show it publicly in the Frameteller gallery. I can withdraw it at any time.'

const STATUS: Record<MyGalleryEntry['status'], string> = {
  checking: 'Checking your storyboard and making its gallery video…',
  published: 'It is in the gallery.',
  pending: 'Waiting for a person to look at it.',
  hidden: 'It is hidden from the gallery for now.',
  failed: 'The gallery video could not be made.',
}

/** "Submit to gallery": consent, a choice of audio, then the entry's status and a way to withdraw it. */
export function GallerySubmit({
  entry,
  ready,
  voiceKept,
  busy,
  error,
  galleryHref,
  onSubmit,
  onWithdraw,
}: {
  entry: MyGalleryEntry | null
  /** Every shot has a panel. */
  ready: boolean
  /** The narration was kept, so "my voice" is possible. */
  voiceKept: boolean
  busy: boolean
  error: string | null
  galleryHref: string
  onSubmit: (audio: GalleryAudio) => void
  onWithdraw: () => void
}) {
  const id = useId()
  const [consent, setConsent] = useState(false)
  const [audio, setAudio] = useState<GalleryAudio>(voiceKept ? 'mine' : 'voice')
  const choices: { value: GalleryAudio; label: string; disabled?: boolean }[] = [
    { value: 'mine', label: 'Publish with my voice', disabled: !voiceKept },
    { value: 'voice', label: 'Publish with the Ava voice instead' },
    { value: 'none', label: 'Publish without audio' },
  ]
  const retry = entry?.status === 'failed'
  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-3 rounded-md border-[1.5px] border-rule bg-sheet p-4" data-testid="gallery-submit">
      <h2 id={`${id}-title`} className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
        Gallery
      </h2>
      {entry && !retry ? (
        <>
          <p className="m-0 text-sm font-semibold" role="status">
            {STATUS[entry.status]}
          </p>
          {entry.note && <p className="m-0 text-sm text-muted">{entry.note}</p>}
          {entry.status === 'published' && (
            <a href={galleryHref} className="text-sm font-semibold underline">
              See it in the gallery{entry.hearts ? ` (${entry.hearts} ${entry.hearts === 1 ? 'heart' : 'hearts'})` : ''}
            </a>
          )}
          <div>
            <Button size="sm" variant="quiet" onClick={onWithdraw} disabled={busy}>
              Withdraw from the gallery
            </Button>
          </div>
        </>
      ) : (
        <>
          {retry && <Notice tone="error" title={STATUS.failed}>{entry.note || 'Try again in a minute.'}</Notice>}
          <p className="m-0 text-sm text-muted">Show your storyboard and animatic to everyone, with captions.</p>
          <fieldset className="m-0 flex flex-col gap-1 border-0 p-0">
            <legend className="mb-1 text-sm font-semibold">Audio</legend>
            {choices.map((c) => (
              <label key={c.value} className="flex items-center gap-2 text-sm">
                <input type="radio" name={`${id}-audio`} value={c.value} checked={audio === c.value} disabled={c.disabled} onChange={() => setAudio(c.value)} />
                {c.label}
                {c.disabled && <span className="text-xs text-muted">(your recording wasn’t kept)</span>}
              </label>
            ))}
          </fieldset>
          <label htmlFor={`${id}-consent`} className="flex items-start gap-2 text-sm">
            <input id={`${id}-consent`} type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 size-4 shrink-0" />
            {CONSENT}
          </label>
          <div>
            <Button size="sm" variant="ink" onClick={() => onSubmit(audio)} disabled={!consent || !ready || busy}>
              {busy ? 'Submitting…' : retry ? 'Try again' : 'Submit to gallery'}
            </Button>
          </div>
          {!ready && <p className="m-0 text-xs text-muted">Every shot needs a panel first.</p>}
        </>
      )}
      {error && <Notice tone="error" title={error} />}
    </section>
  )
}
