import { useCallback, useEffect, useMemo, useState } from 'react'
import { TourCard } from '../../features/tour/components/TourCard'
import { usePresence } from '../../features/tour/hooks/usePresence'
import { view, type Presence } from '../../features/tour/machine'
import { TOUR_STEPS } from '../../features/tour/steps'
import { useTourStore } from '../../features/tour/store'
import { useSampleStory } from '../../features/start/hooks/useStartStory'
import { useStartStore } from '../../features/start/store'
import { navigate, studioPath } from '../router'

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

/** Runs the tour over the real pages: watches for each step's element, and does the steps' actions. */
export function TourHost() {
  const { status, index, dispatch } = useTourStore()
  const state = useMemo(() => ({ status, index }), [status, index])
  const step = TOUR_STEPS[index]
  const target = useCallback((p: Presence) => view(TOUR_STEPS, state, p, 0).target, [state])
  const seen = usePresence(step, target)

  // How long this step has waited: only to say so when a step is slow, never to move on.
  const waiting = view(TOUR_STEPS, state, seen, 0).phase === 'waiting'
  const waitKey = `${index}:${waiting}`
  const [waited, setWaited] = useState({ key: '', s: 0 })
  useEffect(() => {
    if (!waiting) return
    const started = Date.now()
    const timer = setInterval(() => setWaited({ key: waitKey, s: Math.floor((Date.now() - started) / 1000) }), 1000)
    return () => clearInterval(timer)
  }, [waitKey, waiting])
  const waitedS = waited.key === waitKey ? waited.s : 0
  const shown = view(TOUR_STEPS, state, seen, waitedS)

  // The visitor did what the step asked (approved the cast, selected an object): on to the next one.
  useEffect(() => {
    if (step?.doneWhen && seen.done) dispatch({ type: 'done', stepId: step.id })
  }, [step, seen.done, dispatch])

  // Bring the step's element into view when the step, or what it points at, changes.
  useEffect(() => {
    if (!shown.target) return
    document.querySelector(shown.target)?.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' })
  }, [index, shown.target])

  const sample = useSampleStory(
    useCallback(
      (projectId: string) => {
        dispatch({ type: 'next' })
        navigate(studioPath(projectId))
      },
      [dispatch],
    ),
  )
  const act = useCallback(() => {
    if (step?.action?.kind === 'start-sample') return void sample()
    if (step?.action?.kind === 'narrate') {
      dispatch({ type: 'next' }) // the last step: the tour is finished
      useStartStore.getState().set({ mode: 'narrate', script: '' })
      useStartStore.getState().setTitle('')
      navigate('/')
    }
  }, [step, sample, dispatch])

  if (!step) return null
  return (
    <TourCard
      step={step}
      view={shown}
      rect={seen.rect}
      layer={seen.layer}
      onNext={() => dispatch({ type: 'next' })}
      onBack={() => dispatch({ type: 'back' })}
      onSkip={() => dispatch({ type: 'skip' })}
      onAction={act}
    />
  )
}
