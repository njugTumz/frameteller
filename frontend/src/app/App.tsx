import { Button } from '../shared/ui/Button'
import { useEffect } from 'react'
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
import { TopBar } from './TopBar'
import { useTheme } from './theme'

export function App() {
  const route = parseRoute(usePathname())
  useNoindex(route.name !== 'share') // the studio is an app, not content; share pages decide for themselves
  const [theme, setTheme] = useTheme()
  const themeSwitch = <ThemeSwitch value={theme} onChange={setTheme} />
  const paused = useStudioStatus((s) => s.paused)
  useEffect(() => void checkStudioStatus(), [])

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-marker focus:px-3 focus:py-2">
        Skip to the studio
      </a>
      {route.name === 'missing' ? (
        <>
          <TopBar>{themeSwitch}</TopBar>
          <main id="main" className="mx-auto w-full max-w-xl p-4 py-16">
            <Notice tone="warn" title="There is no storyboard at this address." action={<Button onClick={() => navigate('/')}>Start a new story</Button>}>
              Check the link, or start a new story.
            </Notice>
          </main>
        </>
      ) : (
        <>
          <TopBar>{themeSwitch}</TopBar>
          <main id="main" className="flex-1">
            {paused && route.name !== 'share' && route.name !== 'privacy' ? (
              <BackSoonPage />
            ) : route.name === 'privacy' ? (
              <PrivacyPage />
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
    </div>
  )
}
