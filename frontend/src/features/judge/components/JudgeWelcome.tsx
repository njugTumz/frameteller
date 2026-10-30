import { Button } from '../../../shared/ui/Button'
import type { JudgeLinkState } from '../hooks/useJudgeLink'

/** What a judge sees after opening their private link. */
export function JudgeWelcome({ state, onStart, onTour }: { state: JudgeLinkState; onStart: () => void; onTour: () => void }) {
  return (
    <div className="mx-auto w-full max-w-xl px-4 py-16 md:py-24" data-testid="judge-welcome">
      {state.kind === 'checking' && (
        <p className="m-0 text-lg font-semibold" role="status">
          Checking your judge link…
        </p>
      )}
      {state.kind === 'ok' && (
        <>
          <h1 className="m-0 text-4xl font-black tracking-tight widest md:text-5xl">Welcome, judge.</h1>
          <p className="mt-5 text-lg text-muted">
            Judge access is on in this browser{state.until ? ` until ${new Date(state.until).toLocaleDateString()}` : ''}. You skip the
            public queue and the daily limits, and your stories draw from a budget kept for judging.
          </p>
          <p className="mt-4 text-lg">New here? The 2-minute tour runs our sample story with you, through to the animatic.</p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button variant="marker" size="lg" className="font-extrabold" onClick={onTour}>
              Take the 2-minute tour
            </Button>
            <Button size="lg" onClick={onStart}>
              Start a story
            </Button>
          </div>
        </>
      )}
      {state.kind === 'failed' && (
        <>
          <h1 className="m-0 text-3xl font-black tracking-tight">That judge link didn’t work.</h1>
          <p className="mt-4 text-lg text-muted" role="alert">
            {state.message}
          </p>
          <Button className="mt-6" onClick={onStart}>
            Use the public studio
          </Button>
        </>
      )}
    </div>
  )
}
