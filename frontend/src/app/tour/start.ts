import { DEFAULT_VOICE } from '../../features/script/store'
import { SAMPLE_STORY } from '../../features/start/sample'
import { useStartStore } from '../../features/start/store'
import { useTourStore } from '../../features/tour/store'
import { navigate } from '../router'

/** Take the tour: back to the start page with the sample story in "Read it to me" with Ava, then step one. */
export function startTour(): void {
  const start = useStartStore.getState()
  start.setTitle(SAMPLE_STORY.title)
  start.setStyle(SAMPLE_STORY.style)
  start.setNames(SAMPLE_STORY.names)
  start.set({ mode: 'read', script: SAMPLE_STORY.script, format: 'text', voice: DEFAULT_VOICE, language: 'en-US' })
  if (window.location.pathname !== '/') navigate('/')
  useTourStore.getState().dispatch({ type: 'start' })
}
