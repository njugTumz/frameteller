import { useEffect, useRef } from 'react'
import { cx } from '../../../shared/ui/cx'
import type { Paragraph } from '../store'

/**
 * The script as it is told: the current paragraph highlighted and scrolled into view, the next one visible.
 * In "Read it to me" the current paragraph is the one the voice is reading.
 */
export function Teleprompter({
  paragraphs,
  current,
  label,
  spoken = {},
}: {
  paragraphs: Paragraph[]
  current: number
  label: string
  /** "Read it to me" in another language: what the voice says, by paragraph. */
  spoken?: Record<number, string>
}) {
  const list = useRef<HTMLOListElement>(null)
  useEffect(() => {
    const el = list.current?.querySelector<HTMLElement>(`[data-paragraph="${current}"]`)
    el?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  }, [current])
  const episodes = new Set(paragraphs.map((p) => p.episode)).size
  return (
    <section aria-label={label} className="flex flex-col gap-2 rounded-md border-[1.5px] border-rule bg-sheet p-3">
      <h2 className="m-0 text-sm font-bold uppercase tracking-wider text-muted">{label}</h2>
      <ol ref={list} className="m-0 flex max-h-72 list-none flex-col gap-2 overflow-y-auto p-0" data-testid="teleprompter">
        {paragraphs.map((p, i) => {
          const state = p.index === current ? 'current' : p.index === current + 1 ? 'next' : p.index < current ? 'done' : 'later'
          const startsEpisode = episodes > 1 && (i === 0 || paragraphs[i - 1]?.episode !== p.episode)
          return (
            <li key={p.index} data-paragraph={p.index} aria-current={state === 'current' ? 'step' : undefined}>
              {startsEpisode && <p className="m-0 mb-1 text-xs font-bold uppercase tracking-wider text-blue">Episode {p.episode}</p>}
              <p
                data-state={state}
                className={cx(
                  'm-0 rounded-md px-3 py-2 leading-relaxed',
                  state === 'current' && 'border-l-4 border-marker bg-paper text-lg font-semibold text-ink',
                  state === 'next' && 'text-ink',
                  (state === 'done' || state === 'later') && 'text-muted',
                )}
              >
                {spoken[p.index] ?? p.narration}
              </p>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
