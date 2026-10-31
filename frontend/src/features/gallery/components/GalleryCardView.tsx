import { useId, useState } from 'react'
import type { GalleryCard } from '../../../shared/api/types'
import { seconds } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'
import { byline } from '../../../shared/creator'
import { OfficialBadge } from '../../../shared/ui/OfficialBadge'
import { styleName } from '../styles'

/** One storyboard (its media URLs already absolute, see useGallery): its first panel until played, its animatic, a heart, its share page, and Report. */
export function GalleryCardView({
  card,
  reported,
  onHeart,
  onReport,
}: {
  card: GalleryCard
  reported: boolean
  onHeart: () => void
  onReport: (reason: string) => void
}) {
  const id = useId()
  const [playing, setPlaying] = useState(false)
  const [reporting, setReporting] = useState(false)
  const [reason, setReason] = useState('')
  const episodes = card.episodes > 1 ? ` · ${card.episodes} episodes` : ''
  return (
    <li className="flex flex-col overflow-hidden rounded-md border-[1.5px] border-rule bg-sheet" aria-labelledby={`${id}-title`} data-testid="gallery-card">
      <div className="relative aspect-video bg-paper">
        {playing ? (
          <video src={card.video_url} controls autoPlay playsInline className="size-full object-contain" aria-label={`${card.title}, the animatic`} />
        ) : (
          <button type="button" onClick={() => setPlaying(true)} className="group block size-full" aria-label={`Play ${card.title} with sound`}>
            <img src={card.cover_url} alt="" loading="lazy" decoding="async" className="size-full object-cover" />
            <span aria-hidden="true" className="absolute inset-0 m-auto flex h-fit w-fit items-center gap-2 rounded-full bg-ink/85 px-4 py-2 font-bold text-paper group-hover:bg-ink group-focus-visible:bg-ink">
              ▶ Play with sound
            </span>
          </button>
        )}
        {card.featured && <span className="absolute left-2 top-2 rounded bg-marker px-2 py-0.5 text-xs font-bold text-ink">Featured</span>}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-3">
        <h3 id={`${id}-title`} className="m-0 text-base font-bold">
          <a href={card.share_url} className="underline-offset-2 hover:underline pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center">
            {card.title}
          </a>
        </h3>
        <p className="m-0 text-sm" data-testid="gallery-byline">
          {byline(card.creator)}
          {card.creator.official && <OfficialBadge />}
        </p>
        <p className="m-0 text-sm text-muted">
          {styleName(card.style)}
          {episodes} · {card.shots} shots · {seconds(card.duration_ms)}
        </p>
        <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
          <Button
            size="sm"
            variant={card.hearted ? 'ink' : 'outline'}
            aria-pressed={card.hearted}
            aria-label={`${card.hearts} ${card.hearts === 1 ? 'heart' : 'hearts'}${card.hearted ? ', one of them yours' : ', give it a heart'}`}
            onClick={onHeart}
            disabled={card.hearted}
          >
            <span aria-hidden="true">♥ {card.hearts}</span>
          </Button>
          {reported ? (
            <span className="text-xs text-muted">Thanks, we’ll take a look.</span>
          ) : (
            <Button size="sm" variant="quiet" onClick={() => setReporting((r) => !r)} aria-expanded={reporting}>
              Report
            </Button>
          )}
        </div>
        {reporting && !reported && (
          <form
            className="flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              onReport(reason)
              setReporting(false)
            }}
          >
            <label htmlFor={`${id}-reason`} className="text-sm font-semibold">
              What’s wrong with it?
            </label>
            <textarea id={`${id}-reason`} value={reason} maxLength={300} rows={2} onChange={(e) => setReason(e.target.value)} className="rounded border-[1.5px] border-rule bg-paper p-2 text-sm" />
            <div>
              <Button size="sm" type="submit">
                Send report
              </Button>
            </div>
          </form>
        )}
      </div>
    </li>
  )
}
