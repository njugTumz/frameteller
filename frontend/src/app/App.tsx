import { Button } from '../shared/ui/Button'
import { lazy, Suspense, useEffect } from 'react'
import { BackSoonPage } from './pages/BackSoonPage'
import { PrivacyPage } from './pages/PrivacyPage'
import { StartPage } from './pages/StartPage'
import { SharePage } from './pages/SharePage'
import { StudioPage } from './pages/StudioPage'
import { useNoindex } from '../shared/hooks/useNoindex'
import { checkStudioStatus } from '../shared/status/api'
import { useStudioStatus } from '../shared/status/store'
import { Notice } from '../shared/ui/Notice'
import { navigate, parseRoute, usePathname } from './router'
import { ThemeSwitch } from './ThemeSwitch'
import { TopBar, type HeaderAction } from './TopBar'
import { requestReport } from '../features/feedback/store'
import { useTheme } from './theme'
import { JudgePage } from './pages/JudgePage'
import { JudgeBadge } from '../shared/ui/JudgeBadge'
import { TourLayer } from './tour/TourLayer'
import { startTour } from './tour/start'

// Only some visitors open these: they load on demand, so the start page stays small.
const GalleryPage = lazy(() => import('./pages/GalleryPage').then((m) => ({ default: m.GalleryPage })))
const AdminPage = lazy(() => import('./pages/AdminPage').then((m) => ({ default: m.AdminPage })))

export function App() {
  const route = parseRoute(usePathname())
  useNoindex(route.name !== 'share' && route.name !== 'gallery') // the studio is an app; the gallery and share pages are content
  const [theme, setTheme] = useTheme()
  const paused = useStudioStatus((s) => s.paused)
  const judge = useStudioStatus((s) => s.judge)
  const actions: HeaderAction[] = [
    ...(route.name === 'start' || route.name === 'studio' ? [{ label: 'Take the tour', onSelect: startTour }] : []),
    ...(route.name !== 'gallery' ? [{ label: 'Gallery', href: '/gallery' }] : []),
  ]
  // On phones the menu also holds what the wide layout shows in the page.
  const menuOnly: HeaderAction[] = [
    ...(route.name === 'studio' ? [{ label: 'Report a problem', onSelect: requestReport }] : []),
    ...(route.name !== 'privacy' ? [{ label: 'Privacy', href: '/privacy' }] : []),
  ]
  const bar = (
    <TopBar
      badge={judge && <JudgeBadge />}
      actions={actions}
      menuOnly={menuOnly}
      theme={(place) => <ThemeSwitch value={theme} onChange={setTheme} place={place} />}
    />
  )
  useEffect(() => void checkStudioStatus(), [])

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-marker focus:px-3 focus:py-2">
        Skip to the studio
      </a>
      {route.name === 'missing' ? (
        <>
          {bar}
          <main id="main" className="mx-auto w-full max-w-xl p-4 py-16">
            <Notice tone="warn" title="There is no storyboard at this address." action={<Button onClick={() => navigate('/')}>Start a new story</Button>}>
              Check the link, or start a new story.
            </Notice>
          </main>
        </>
      ) : (
        <>
          {bar}
          <main id="main" className="flex-1">
            {paused && route.name !== 'share' && route.name !== 'privacy' ? (
              <BackSoonPage />
            ) : route.name === 'privacy' ? (
              <PrivacyPage />
            ) : route.name === 'judge' ? (
              <JudgePage />
            ) : route.name === 'gallery' || route.name === 'admin' ? (
              <Suspense fallback={<p className="p-4 text-muted">Loading…</p>}>{route.name === 'gallery' ? <GalleryPage /> : <AdminPage />}</Suspense>
            ) : route.name === 'start' ? (
              <StartPage />
            ) : route.name === 'share' ? (
              <SharePage key={route.token} token={route.token} />
            ) : (
              <StudioPage key={route.projectId} projectId={route.projectId} />
            )}
          </main>
        </>
      )}
      <TourLayer />
    </div>
  )
}
