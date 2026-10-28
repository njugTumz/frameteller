import { useCallback, useEffect } from 'react'
import { useBeatShortcut } from '../../features/recording/hooks/useBeatShortcut'
import { useNarration } from '../../features/recording/hooks/useNarration'
import { Notices, ProblemNotice } from '../../features/recording/components/ProblemNotice'
import { TellingControls } from '../../features/recording/components/TellingControls'
import { TranscriptRail } from '../../features/recording/components/TranscriptRail'
import { useRecordingStore } from '../../features/recording/store'
import { ShotCard } from '../../features/storyboard/components/ShotCard'
import { StoryboardGrid } from '../../features/storyboard/components/StoryboardGrid'
import { useAutoDraft } from '../../features/storyboard/hooks/useAutoDraft'
import { useProjectSync } from '../../features/storyboard/hooks/useProjectSync'
import { panelPhase, useStoryboardStore } from '../../features/storyboard/store'
import type { Project, Shot } from '../../shared/api/types'
import { mediaUrl } from '../../shared/api/client'
import type { ServerEvent } from '../../shared/events'
import { loadNames } from '../../shared/keywords'

const NO_KEYWORDS: readonly string[] = []

/** Fan one server event out to every feature store. */
function dispatch(e: ServerEvent): void {
  useStoryboardStore.getState().apply(e)
}

function loaded(p: Project): void {
  const r = useRecordingStore.getState()
  if (r.turns.length === 0) r.loadTurns(p.turns)
}

const notYet = (_s: Shot) => false

export function StudioPage({ projectId }: { projectId: string }) {
  const r = useRecordingStore()
  const board = useStoryboardStore()
  const sync = useProjectSync(projectId, r.connected, loaded)
  const narration = useNarration(projectId, NO_KEYWORDS, dispatch)
  const beat = useCallback(() => void narration.beat(), [narration])
  useBeatShortcut(r.telling === 'live', beat)
  useAutoDraft(projectId, notYet)

  useEffect(() => {
    useStoryboardStore.getState().reset()
    const s = useRecordingStore.getState()
    s.reset()
    s.setKeywords(loadNames(projectId))
  }, [projectId])

  return (
    <div className="grid gap-6 p-4 lg:grid-cols-[340px_1fr] lg:p-6">
      <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:max-h-[calc(100dvh-6rem)] lg:self-start lg:overflow-y-auto">
        {r.problem && <ProblemNotice problem={r.problem} onRetry={() => void narration.start()} onDismiss={() => r.setProblem(null)} />}
        <TellingControls telling={r.telling} level={r.level} beats={r.beats} onStart={() => void narration.start()} onStop={() => narration.stop()} onBeat={beat} />
        <Notices notices={r.notices} onDismiss={r.dismissNotice} />
        <TranscriptRail turns={r.turns} partial={r.partial} listening={r.telling === 'live'} correcting={r.correcting} onCorrect={(id, text) => narration.correct(id, text)} />
      </aside>
      <div className="flex min-w-0 flex-col gap-6">
        {sync.status === 'loading' && <p className="m-0 text-muted">Opening the storyboard…</p>}
        <StoryboardGrid count={board.shots.length} telling={r.telling === 'live'}>
          {board.shots.map((shot) => {
            const phase = panelPhase(shot, board.jobs[shot.id], false)
            return (
              <ShotCard
                key={shot.id}
                shot={shot}
                phase={phase}
                imageSrc={phase.kind === 'ready' ? mediaUrl(phase.imageUrl) : null}
                names={shot.character_ids}
                onOpen={() => undefined}
                onRetry={() => undefined}
              />
            )
          })}
        </StoryboardGrid>
      </div>
    </div>
  )
}
