import { useCallback, useEffect } from 'react'
import { useBeatShortcut } from '../../features/recording/hooks/useBeatShortcut'
import { useNarration } from '../../features/recording/hooks/useNarration'
import { Notices, ProblemNotice } from '../../features/recording/components/ProblemNotice'
import { TellingControls } from '../../features/recording/components/TellingControls'
import { TranscriptRail } from '../../features/recording/components/TranscriptRail'
import { useRecordingStore } from '../../features/recording/store'
import { loadNames } from '../../shared/keywords'
import type { ServerEvent } from '../../shared/events'

const NO_KEYWORDS: readonly string[] = []

export function StudioPage({ projectId }: { projectId: string }) {
  const r = useRecordingStore()
  const onEvent = useCallback((_e: ServerEvent) => undefined, [])
  const narration = useNarration(projectId, NO_KEYWORDS, onEvent)
  const beat = useCallback(() => void narration.beat(), [narration])
  useBeatShortcut(r.telling === 'live', beat)

  useEffect(() => {
    const s = useRecordingStore.getState()
    s.reset()
    s.setKeywords(loadNames(projectId))
  }, [projectId])

  return (
    <div className="grid gap-4 p-4 lg:grid-cols-[340px_1fr] lg:p-6">
      <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:max-h-[calc(100dvh-6rem)] lg:overflow-y-auto">
        {r.problem && <ProblemNotice problem={r.problem} onRetry={() => void narration.start()} onDismiss={() => r.setProblem(null)} />}
        <TellingControls telling={r.telling} level={r.level} beats={r.beats} onStart={() => void narration.start()} onStop={() => narration.stop()} onBeat={beat} />
        <Notices notices={r.notices} onDismiss={r.dismissNotice} />
        <TranscriptRail turns={r.turns} partial={r.partial} listening={r.telling === 'live'} correcting={r.correcting} onCorrect={(id, text) => narration.correct(id, text)} />
      </aside>
      <section aria-label="Storyboard" className="min-h-64" />
    </div>
  )
}
