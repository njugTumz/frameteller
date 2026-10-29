import { Suspense, lazy, useCallback, useEffect, useMemo } from 'react'
import { castReadyFor, useCastStore } from '../../features/cast/store'
import { storyboardPdfUrl, shareUrl } from '../../features/export/api'
import { ExportPanel } from '../../features/export/components/ExportPanel'
import { SharePanel } from '../../features/export/components/SharePanel'
import { useExport } from '../../features/export/hooks/useExport'
import { Notices, ProblemNotice } from '../../features/recording/components/ProblemNotice'
import { RecordingKept } from '../../features/recording/components/RecordingKept'
import { SilenceNotice } from '../../features/recording/components/SilenceNotice'
import { UpdatingNotice } from '../../features/recording/components/UpdatingNotice'
import { useAudioInputs } from '../../features/recording/hooks/useAudioInputs'
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
import type { Project, Shot } from '../../shared/api/types'
import { loadKeepAudio } from '../../shared/consent'
import { loadNames } from '../../shared/keywords'
import { useEditorStore } from '../../features/panel-editor/store'
import { NeedsYourEye } from '../../features/supervisor/components/NeedsYourEye'
import { ReviewBadge } from '../../features/supervisor/components/ReviewBadge'
import { SupervisorFeed } from '../../features/supervisor/components/SupervisorFeed'
import { useSupervisorActions } from '../../features/supervisor/hooks/useSupervisorActions'
import { CastZone } from '../studio/CastZone'
import { dispatchEvent, projectLoaded, resetStudio } from '../studio/dispatch'

// The editor brings react-konva; load it the first time a panel is opened.
const EditorZone = lazy(() => import('../studio/EditorZone').then((m) => ({ default: m.EditorZone })))

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
  const editing = useEditorStore((s) => s.shotId)
  const nameOf = (id: string) => cast.characters.find((c) => c.id === id)?.name ?? id
  const onProject = useCallback((p: Project) => {
    useStoryboardStore.getState().load(p)
    projectLoaded(p)
  }, [])
  const exporting = useExport(projectId, onProject)
  const supervisor = useSupervisorActions(projectId, onProject)
  const inputs = useAudioInputs(r.silent)
  const allDrawn = board.shots.length > 0 && board.shots.every((s) => s.panel?.status === 'ready')
  const kept = board.narrations.reduce((ms, n) => ms + n.duration_ms, 0)

  useEffect(() => {
    resetStudio()
    useRecordingStore.getState().setKeywords(loadNames(projectId))
    useRecordingStore.getState().set({ keepAudio: loadKeepAudio(projectId) })
  }, [projectId])

  return (
    <div className="grid gap-6 p-4 lg:grid-cols-[340px_1fr] lg:p-6">
      <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:max-h-[calc(100dvh-6rem)] lg:self-start lg:overflow-y-auto">
        {r.updating && <UpdatingNotice />}
        {r.problem && <ProblemNotice problem={r.problem} onRetry={() => void narration.start()} onDismiss={() => r.setProblem(null)} />}
        {r.silent && (
          <SilenceNotice
            micLabel={r.micLabel}
            inputs={inputs}
            deviceId={r.deviceId}
            onPick={(deviceId) => void narration.useMicrophone(deviceId)}
            onDismiss={() => r.set({ silent: false })}
          />
        )}
        <TellingControls telling={r.telling} heardNothing={r.heardNothing} level={r.level} beats={r.beats} onStart={() => void narration.start()} onStop={() => narration.stop()} onBeat={beat} />
        <Notices notices={r.notices} onDismiss={r.dismissNotice} />
        {kept > 0 && <RecordingKept durationMs={kept} onDelete={() => void exporting.forgetRecording()} />}
        {(board.shots.length > 0 || board.supervisor.length > 0) && (
          <SupervisorFeed
            entries={board.supervisor}
            enabled={board.continuityChecks}
            busy={supervisor.busy === 'toggle'}
            error={supervisor.error}
            onToggle={(enabled) => {
              useStoryboardStore.getState().set({ continuityChecks: enabled }) // at once; undone if it fails
              void supervisor.toggle(enabled).then((ok) => ok || useStoryboardStore.getState().set({ continuityChecks: !enabled }))
            }}
          />
        )}
        <TranscriptRail turns={r.turns} partial={r.partial} listening={r.telling === 'live'} correcting={r.correcting} onCorrect={(id, text) => narration.correct(id, text)} />
      </aside>
      <div className="flex min-w-0 flex-col gap-6">
        {sync.status === 'loading' && <p className="m-0 text-muted">Opening the storyboard…</p>}
        <CastZone projectId={projectId} onProject={onProject} />
        <StoryboardGrid count={board.shots.length} telling={r.telling === 'live'}>
          {board.shots.map((shot) => {
            const phase = panelPhase(shot, board.jobs[shot.id], castReadyFor(cast, shot))
            const review = shot.panel?.review ?? null
            return (
              <ShotCard
                key={shot.id}
                shot={shot}
                phase={phase}
                imageSrc={phase.kind === 'ready' ? mediaUrl(phase.imageUrl) : null}
                names={shot.character_ids.map(nameOf)}
                composing={board.composing[shot.id] === 'queued' || board.composing[shot.id] === 'running'}
                badge={review ? <ReviewBadge review={review} /> : null}
                review={
                  review?.outcome === 'needs_user' ? (
                    <NeedsYourEye
                      review={review}
                      busy={supervisor.busy !== null}
                      onApply={() => void supervisor.applyFix(shot)}
                      onAccept={() => void supervisor.accept(shot)}
                      onRedraw={() => void draw(shot, 'draft')}
                    />
                  ) : null
                }
                onOpen={() => useEditorStore.getState().open(shot.id, shot.panel?.revision ?? null)}
                onRetry={() => void draw(shot, 'draft')}
              />
            )
          })}
        </StoryboardGrid>
        {board.shots.length > 0 && (
          <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
            <ExportPanel
              ready={allDrawn}
              job={board.exportJob}
              animatic={board.animatic}
              videoSrc={mediaUrl(board.animatic?.url)}
              downloadHref={board.animatic ? `${mediaUrl(board.animatic.url)}?download=1` : null}
              pdfHref={storyboardPdfUrl(projectId)}
              voiceKept={kept > 0}
              error={exporting.error}
              onExport={(subtitles) => void exporting.animatic(subtitles)}
            />
            <SharePanel
              link={board.shareToken ? shareUrl(board.shareToken) : null}
              isPublic={board.sharePublic}
              busy={exporting.sharing}
              onShare={(isPublic) => void exporting.share(isPublic)}
              onRevoke={() => void exporting.unshare()}
            />
          </div>
        )}
      </div>
      {editing && (
        <Suspense fallback={null}>
          <EditorZone projectId={projectId} />
        </Suspense>
      )}
    </div>
  )
}
