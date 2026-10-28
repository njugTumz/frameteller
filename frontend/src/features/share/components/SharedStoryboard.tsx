import type { SharedProject } from '../../../shared/api/types'
import { framingLabel, seconds, shotLabel } from '../../../shared/format'
import { Button } from '../../../shared/ui/Button'

/** What a share link shows: the animatic if there is one, then every shot. Nothing can be changed here. */
export function SharedStoryboard({
  project,
  src,
  onMakeYourOwn,
}: {
  project: SharedProject
  src: (path: string | null | undefined) => string | null
  onMakeYourOwn: () => void
}) {
  const video = src(project.animatic?.url)
  return (
    <article className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8" data-testid="shared-storyboard">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="m-0 text-sm font-bold uppercase tracking-wider text-muted">A storyboard told out loud</p>
          <h1 className="m-0 text-4xl font-black widest">{project.title || 'Untitled story'}</h1>
        </div>
        <Button variant="marker" size="lg" onClick={onMakeYourOwn} className="font-extrabold">
          Make your own
        </Button>
      </header>
      {video && (
        <section aria-label="Animatic" className="flex flex-col gap-1">
          <video src={video} controls preload="metadata" className="frame w-full" data-testid="shared-animatic" aria-label="The animatic" />
          <p className="m-0 text-sm text-muted">Animatic · {seconds(project.animatic?.duration_ms ?? 0)}</p>
        </section>
      )}
      <ol className="m-0 grid list-none gap-x-5 gap-y-8 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {project.shots.map((shot) => {
          const image = src(shot.image_url)
          return (
            <li key={shot.number} className="flex flex-col gap-2" data-testid="shared-shot">
              <div className="frame aspect-video">
                {image ? (
                  <img src={image} alt={`Shot ${shot.number}: ${shot.action}`} className="size-full object-cover" />
                ) : (
                  <div className="grid size-full place-items-center text-sm text-muted">Not drawn yet</div>
                )}
              </div>
              <header className="flex items-baseline justify-between gap-2 text-sm text-muted tabular">
                <h2 className="m-0 text-base font-extrabold text-ink wide">Shot {shotLabel(shot.number)}</h2>
                <span>
                  {framingLabel(shot.framing)} · {seconds(shot.duration_ms)}
                </span>
              </header>
              <p className="m-0 leading-snug">{shot.action}</p>
              {shot.dialogue && <p className="m-0 border-l-2 border-blue pl-2 text-muted italic">“{shot.dialogue}”</p>}
            </li>
          )
        })}
      </ol>
    </article>
  )
}
