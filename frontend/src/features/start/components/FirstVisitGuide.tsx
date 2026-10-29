import { Button } from '../../../shared/ui/Button'

const STEPS = [
  { title: 'Tell it', text: 'Speak your story, or let a voice read your script. Press Next shot between beats.' },
  { title: 'Approve the cast', text: 'Check each character’s sheet. Every panel copies it, so fix it here.' },
  { title: 'Watch it back', text: 'The panels draw themselves. Export an animatic timed to the telling, with captions.' },
]

/** How Frameteller works, in three steps, on a browser's first visit. */
export function FirstVisitGuide({ onDismiss }: { onDismiss: () => void }) {
  return (
    <section aria-labelledby="guide-title" className="mb-6 rounded-md border-[1.5px] border-rule bg-wash p-4">
      <div className="flex items-start justify-between gap-3">
        <h2 id="guide-title" className="m-0 text-base font-bold">
          How it works
        </h2>
        <Button size="sm" variant="quiet" onClick={onDismiss}>
          Got it
        </Button>
      </div>
      <ol className="m-0 mt-2 grid list-none gap-3 p-0 sm:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="flex gap-2">
            <span aria-hidden="true" className="flex size-7 shrink-0 items-center justify-center rounded-full bg-ink text-sm font-bold text-paper">
              {i + 1}
            </span>
            <span className="text-sm">
              <strong className="block">{s.title}</strong>
              {s.text}
            </span>
          </li>
        ))}
      </ol>
    </section>
  )
}
