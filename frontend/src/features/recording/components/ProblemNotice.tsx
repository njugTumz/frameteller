import { Button } from '../../../shared/ui/Button'
import { Notice } from '../../../shared/ui/Notice'
import type { Problem } from '../store'

const HELP: Record<Problem['kind'], { title: string; body: string }> = {
  'mic-blocked': {
    title: 'Allow the microphone to start telling.',
    body: 'Click the lock or microphone icon in the address bar, set Microphone to Allow, then press Start telling again. On a phone, allow it in the browser’s site settings.',
  },
  'mic-missing': {
    title: 'Plug in a microphone to start telling.',
    body: 'No microphone was found. Connect one (a headset works well), or pick one in your system sound settings, then press Start telling.',
  },
  'mic-busy': {
    title: 'Another app is holding the microphone.',
    body: 'Video calls often keep it. Close that app or call, then press Start telling.',
  },
  'mic-unsupported': {
    title: 'Open the studio in a recent browser to record.',
    body: 'Use current Chrome, Edge, Firefox or Safari, on an https address.',
  },
  'mic-lost': {
    title: 'The microphone was disconnected.',
    body: 'Everything you said before that is kept. Plug it back in and press Tell more to carry on.',
  },
  connection: { title: 'The studio connection stopped.', body: 'Everything directed so far is saved. Press Start telling to carry on.' },
  server: { title: 'The studio stopped this session.', body: 'Everything directed so far is saved. Press Start telling to carry on.' },
}

export function ProblemNotice({ problem, onRetry, onDismiss }: { problem: Problem; onRetry: () => void; onDismiss: () => void }) {
  const help = HELP[problem.kind]
  const detail = problem.kind === 'connection' || problem.kind === 'server' ? problem.message : null
  return (
    <Notice
      tone="error"
      title={help.title}
      action={
        <>
          <Button size="sm" variant="ink" onClick={onRetry}>
            Start telling
          </Button>
          <Button size="sm" onClick={onDismiss}>
            Dismiss
          </Button>
        </>
      }
    >
      {detail && <p className="m-0 mb-1 text-ink">{detail}</p>}
      <p className="m-0">{help.body}</p>
    </Notice>
  )
}

export function Notices({ notices, onDismiss }: { notices: string[]; onDismiss: (n: string) => void }) {
  if (!notices.length) return null
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {notices.map((n) => (
        <li key={n}>
          <Notice tone="warn" title={n} action={<Button size="sm" variant="quiet" onClick={() => onDismiss(n)}>Dismiss</Button>} />
        </li>
      ))}
    </ul>
  )
}
