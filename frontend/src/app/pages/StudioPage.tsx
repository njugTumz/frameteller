import { useCallback, useEffect, useMemo } from 'react'
import { castReadyFor, useCastStore } from '../../features/cast/store'
import { Notices, ProblemNotice } from '../../features/recording/components/ProblemNotice'
import { TellingControls } from '../../features/recording/components/TellingControls'
import { TranscriptRail } from '../../features/recording/components/TranscriptRail'
import { useBeatShortcut } from '../../features/recording/hooks/useBeatShortcut'
import { useNarration } from '../../features/recording/hooks/useNarration'
import { useRecordingStore } from '../../features/recording/store'
import { ShotCard } from '../../features/storyboard/components/ShotCard'
import { StoryboardGrid } from '../../features/storyboard/components/StoryboardGrid'
import { useAutoDraft } from '../../features/storyboard/hooks/useAutoDraft'
import { usePanelRender } from '../../features/storyboard/hooks/usePanelRender'
import { useProjectSync } from '../../features/storyboard/hooks/useProjectSync'
import { panelPhase, useStoryboardStore } from '../../features/storyboard/store'
import { mediaUrl } from '../../shared/api/client'
import type { Shot } from '../../shared/api/types'
import { loadNames } from '../../shared/keywords'
import { CastZone } from '../studio/CastZone'
import { dispatchEvent, projectLoaded, resetStudio } from '../studio/dispatch'

export function StudioPage({ projectId }: { projectId: string }) {
  const r = useRecordingStore()
  const board = useStoryboardStore()
  const cast = useCastStore()
  const castNames = useMemo(() => cast.characters.map((c) => c.name), [cast.characters])
  const sync = useProjectSync(projectId, r.connected, projectLoaded)
  const narration = useNarration(projectId, castNames, dispatchEvent)
  const beat = useCallback(() => void narration.beat(), [narration])
  useBeatShortcut(r.telling === 'live', beat)

  const canDraw = useCallback((shot: Shot) => castReadyFor(cast, shot), [cast])
  useAutoDraft(projectId, canDraw)
  const draw = usePanelRender(projectId)
  const nameOf = (id: string) => cast.characters.find((c) => c.id === id)?.name ?? id

  useEffect(() => {
    resetStudio()
    useRecordingStore.getState().setKeywords(loadNames(projectId))
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
        <CastZone projectId={projectId} />
        <StoryboardGrid count={board.shots.length} telling={r.telling === 'live'}>
          {board.shots.map((shot) => {
            const phase = panelPhase(shot, board.jobs[shot.id], castReadyFor(cast, shot))
            return (
              <ShotCard
                key={shot.id}
                shot={shot}
                phase={phase}
                imageSrc={phase.kind === 'ready' ? mediaUrl(phase.imageUrl) : null}
                names={shot.character_ids.map(nameOf)}
                onOpen={() => undefined}
                onRetry={() => void draw(shot, 'draft')}
              />
            )
          })}
        </StoryboardGrid>
      </div>
    </div>
  )
}
