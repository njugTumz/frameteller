import { useId } from 'react'
import type { GalleryCard, GalleryCountry, PanelStyle } from '../../../shared/api/types'
import { country as countryLabel } from '../../../shared/creator'
import { Notice } from '../../../shared/ui/Notice'
import type { GalleryView } from '../api'
import { STYLE_NAMES } from '../styles'
import { GalleryCardView } from './GalleryCardView'

const VIEWS: { value: GalleryView; label: string }[] = [
  { value: 'featured', label: 'Featured' },
  { value: 'newest', label: 'Newest' },
]

const chip = (on: boolean) =>
  `rounded-full border-[1.5px] px-3 py-1 text-sm font-semibold pointer-coarse:min-h-11 ${on ? 'border-ink bg-ink text-paper' : 'border-rule bg-sheet text-ink'}`

/** The public gallery: how many countries its stories come from, filters, then the cards. */
export function GalleryGrid({
  view,
  style,
  country,
  countries,
  cards,
  error,
  reported,
  onView,
  onStyle,
  onCountry,
  onHeart,
  onReport,
}: {
  view: GalleryView
  style: PanelStyle | null
  country: string | null
  /** Creator countries across the whole gallery, most entries first. */
  countries: GalleryCountry[]
  cards: GalleryCard[] | null
  error: string | null
  reported: Set<string>
  onView: (v: GalleryView) => void
  onStyle: (s: PanelStyle | null) => void
  onCountry: (code: string | null) => void
  onHeart: (id: string) => void
  onReport: (id: string, reason: string) => void
}) {
  const id = useId()
  return (
    <div className="flex flex-col gap-4">
      {countries.length > 0 && (
        <p className="m-0 text-sm font-semibold" data-testid="country-count">
          Stories from {countries.length} {countries.length === 1 ? 'country' : 'countries'}
        </p>
      )}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter the gallery">
        {VIEWS.map((v) => (
          <button key={v.value} type="button" className={chip(view === v.value)} aria-pressed={view === v.value} onClick={() => onView(v.value)}>
            {v.label}
          </button>
        ))}
        <span aria-hidden="true" className="mx-1 border-l border-rule" />
        <button type="button" className={chip(style === null)} aria-pressed={style === null} onClick={() => onStyle(null)}>
          Every style
        </button>
        {(Object.keys(STYLE_NAMES) as PanelStyle[]).map((s) => (
          <button key={s} type="button" className={chip(style === s)} aria-pressed={style === s} onClick={() => onStyle(s)}>
            {STYLE_NAMES[s]}
          </button>
        ))}
        {countries.length > 0 && (
          <>
            <span aria-hidden="true" className="mx-1 border-l border-rule" />
            <label htmlFor={`${id}-country`} className="sr-only">
              Country
            </label>
            <select
              id={`${id}-country`}
              value={country ?? ''}
              onChange={(e) => onCountry(e.target.value || null)}
              className="rounded-full border-[1.5px] border-rule bg-sheet px-3 py-1 text-sm font-semibold text-ink"
            >
              <option value="">Every country</option>
              {countries.map((c) => (
                <option key={c.code} value={c.code}>
                  {countryLabel(c.code)} ({c.entries})
                </option>
              ))}
            </select>
          </>
        )}
      </div>
      {error && <Notice tone="error" title={error} />}
      {cards === null && !error && <p className="m-0 text-muted" role="status">Loading the gallery…</p>}
      {cards?.length === 0 && <p className="m-0 text-muted">No storyboards here yet. Tell a story and submit yours.</p>}
      {cards && cards.length > 0 && (
        <ul className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3" aria-label="Storyboards">
          {cards.map((c) => (
            <GalleryCardView key={c.id} card={c} reported={reported.has(c.id)} onHeart={() => onHeart(c.id)} onReport={(r) => onReport(c.id, r)} />
          ))}
        </ul>
      )}
    </div>
  )
}
