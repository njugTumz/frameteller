import { Button } from '../../../shared/ui/Button'

/** On a first visit (and first for judges): the offer of the guided tour, in place of the three-step guide. */
export function TourOffer({ onTake, onDismiss }: { onTake: () => void; onDismiss: () => void }) {
  return (
    <section aria-labelledby="tour-offer-title" className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-md border-[1.5px] border-rule bg-wash p-4" data-testid="tour-offer">
      <div>
        <h2 id="tour-offer-title" className="m-0 text-base font-bold">
          New here? Take the 2-minute tour
        </h2>
        <p className="m-0 text-sm text-muted">It runs our sample story with you, step by step, through to the animatic.</p>
      </div>
      <div className="flex gap-2">
        <Button variant="quiet" size="sm" onClick={onDismiss}>
          No thanks
        </Button>
        <Button variant="ink" size="sm" onClick={onTake}>
          Take the tour
        </Button>
      </div>
    </section>
  )
}
