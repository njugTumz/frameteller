import type { GalleryCard, PanelStyle } from '../../../shared/api/types'
import { Notice } from '../../../shared/ui/Notice'
import type { GalleryView } from '../api'
import { STYLE_NAMES } from '../styles'
import { GalleryCardView } from './GalleryCardView'

const VIEWS: { value: GalleryView; label: string }[] = [
  { value: 'featured', label: 'Featured' },
  { value: 'newest', label: 'Newest' },
]

const chip = (on: boolean) =>
  `rounded-full border-[1.5px] px-3 py-1 text-sm font-semibold ${on ? 'border-ink bg-ink text-paper' : 'border-rule bg-sheet text-ink'}`

/** The public gallery: filters, then the cards. */
export function GalleryGrid({
  view,
  style,
  cards,
  error,
  reported,
  onView,
  onStyle,
  onHeart,
  onReport,
}: {
  view: GalleryView
  style: PanelStyle | null
  cards: GalleryCard[] | null
  error: string | null
  reported: Set<string>
  onView: (v: GalleryView) => void
  onStyle: (s: PanelStyle | null) => void
  onHeart: (id: string) => void
  onReport: (id: string, reason: string) => void
}) {
  return (
    <div className="flex flex-col gap-4">
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
