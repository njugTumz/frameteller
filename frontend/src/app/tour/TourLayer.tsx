import { Component, Suspense, lazy, type ReactNode } from 'react'
import { useTourStore } from '../../features/tour/store'

// The tour loads only when someone takes it, so the first visit stays small.
const TourHost = lazy(() => import('./TourHost').then((m) => ({ default: m.TourHost })))

/** If the tour cannot load (an old cached page, a dropped connection), the start page shows the simple guide. */
class TourBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  override componentDidCatch() {
    useTourStore.getState().setFailed()
  }

  override render() {
    return this.state.failed ? null : this.props.children
  }
}

export function TourLayer() {
  const running = useTourStore((s) => s.status === 'running')
  if (!running) return null
  return (
    <TourBoundary>
      <Suspense fallback={null}>
        <TourHost />
      </Suspense>
    </TourBoundary>
  )
}
