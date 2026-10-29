import { sharedUrl } from '../../features/share/api'
import { SharedStoryboard } from '../../features/share/components/SharedStoryboard'
import { useShared } from '../../features/share/hooks/useShared'
import { useNoindex } from '../../shared/hooks/useNoindex'
import { Button } from '../../shared/ui/Button'
import { Notice } from '../../shared/ui/Notice'
import { navigate } from '../router'

export function SharePage({ token }: { token: string }) {
  const shared = useShared(token)
  useNoindex(shared.status !== 'ready' || !shared.project.public) // unlisted unless the owner made it public
  const makeYourOwn = () => navigate('/')
  if (shared.status === 'loading') return <p className="mx-auto max-w-xl p-4 py-16 text-muted">Opening the storyboard…</p>
  if (shared.status !== 'ready') {
    return (
      <div className="mx-auto w-full max-w-xl p-4 py-16">
        <Notice
          tone="warn"
          title={shared.status === 'gone' ? 'This link was turned off, or never existed.' : shared.message}
          action={<Button onClick={makeYourOwn}>Make your own</Button>}
        >
          Ask the storyteller for a new link, or tell a story of your own.
        </Notice>
      </div>
    )
  }
  return <SharedStoryboard project={shared.project} src={sharedUrl} onMakeYourOwn={makeYourOwn} />
}
