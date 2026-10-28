import type { ReactNode } from 'react'

export function StoryboardGrid({ count, children, telling }: { count: number; children: ReactNode; telling: boolean }) {
  return (
    <section aria-labelledby="storyboard-title" className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="storyboard-title" className="m-0 text-sm font-bold uppercase tracking-wider text-muted">
          Storyboard
        </h2>
        <span className="text-sm text-muted tabular" aria-live="polite">
          {count} {count === 1 ? 'shot' : 'shots'}
        </span>
      </div>
      {count === 0 ? (
        <div className="grid place-items-center rounded-md border-2 border-dashed border-rule bg-sheet/70 px-6 py-16 text-center">
          <p className="m-0 max-w-[44ch] text-muted">
            {telling
              ? 'Keep going. When you press Next shot, the words since the last cut become a shot here.'
              : 'Your shots appear here as you tell the story. Press Start telling, describe the first shot, then press Next shot in the pause before the next one.'}
          </p>
        </div>
      ) : (
        <ol className="m-0 grid list-none gap-x-5 gap-y-8 p-0 sm:grid-cols-2 2xl:grid-cols-3">{children}</ol>
      )}
    </section>
  )
}
