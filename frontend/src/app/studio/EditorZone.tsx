import { useCallback, useEffect } from 'react'
import { EditBox } from '../../features/panel-editor/components/EditBox'
import { PanelCanvas } from '../../features/panel-editor/components/PanelCanvas'
import { PanelEditor } from '../../features/panel-editor/components/PanelEditor'
import { useDictation } from '../../features/panel-editor/hooks/useDictation'
import { usePanelEditor } from '../../features/panel-editor/hooks/usePanelEditor'
import { movesFromLayers, usePanelLayers } from '../../features/panel-editor/hooks/usePanelLayers'
import { NO_MOVE, moveKey, useEditorStore } from '../../features/panel-editor/store'
import { usePanelRender } from '../../features/storyboard/hooks/usePanelRender'
import { panelPhase, useStoryboardStore } from '../../features/storyboard/store'
import { mediaUrl } from '../../shared/api/client'
import type { Mask, Shot, Ticket } from '../../shared/api/types'

const PANEL = { width: 1920, height: 1280 } // Muse Image's 3:2 output (ADR 0003), until the panel reports its size

function queued(shot: Shot, ticket: Ticket): void {
  useStoryboardStore.getState().jobStarted(shot.id, { kind: 'edit_panel', status: 'queued', revision: ticket.revision, message: null })
}

export function EditorZone({ projectId }: { projectId: string }) {
  const editor = useEditorStore()
  const shot = useStoryboardStore((s) => s.shots.find((x) => x.id === editor.shotId) ?? null)
  const job = useStoryboardStore((s) => (editor.shotId ? s.jobs[editor.shotId] : undefined))
  const draw = usePanelRender(projectId)
  const actions = usePanelEditor(projectId, shot, queued, draw)
  const dictation = useDictation(projectId)
  const layers = usePanelLayers(projectId, shot)
  const composing = useStoryboardStore((s) => (editor.shotId ? s.composing[editor.shotId] : undefined))
  const revision = shot?.panel?.revision ?? null

  useEffect(() => {
    useEditorStore.getState().revisionChanged(revision)
  }, [revision])

  const close = useCallback(() => useEditorStore.getState().close(), [])
  if (!shot?.panel?.image_url || revision === null) return null

  const panel = shot.panel
  const phase = panelPhase(shot, job, true)
  const size = panel.width && panel.height ? { width: panel.width, height: panel.height } : PANEL
  // Saved layers first, then moves made here that the server has not confirmed yet.
  const moves = Object.fromEntries(
    Object.entries({ ...movesFromLayers(panel.layers), ...editor.moves[moveKey(shot.id, revision)] }).filter(([, m]) => m.dx !== 0 || m.dy !== 0 || m.scale !== 1),
  )
  const known = new Map<string, Mask>(panel.masks.map((m) => [m.id, m]))
  if (editor.selection) known.set(editor.selection.mask.id, editor.selection.mask)
  const layer = (m: Mask) => ({ mask: m, cutoutSrc: mediaUrl(m.cutout_url), move: moves[m.id] ?? NO_MOVE })
  const selected = editor.selection ? layer(editor.selection.mask) : null
  const selectMask = (m: Mask) => editor.set({ selection: { mask: m, cached: true, ms: 0 }, selectError: null })

  return (
    <PanelEditor
      view={{
        shot,
        revision,
        drawing: phase.kind === 'drawing' ? phase.what : phase.kind === 'queued' ? (job?.kind === 'edit_panel' ? 'change' : 'final') : null,
        failed: phase.kind === 'failed' ? phase.message : null,
        selection: editor.selection,
        selecting: editor.selecting,
        selectError: editor.selectError,
        masks: [...known.values()],
        hasMoves: Object.keys(moves).length > 0,
        before: editor.before,
        showBefore: editor.showBefore,
        beforeSrc: mediaUrl(editor.before?.imageUrl),
        editError: editor.editError,
        preparing: composing === 'queued' || composing === 'running',
      }}
      canvas={
        <PanelCanvas
          imageSrc={mediaUrl(panel.base_image_url ?? panel.image_url) ?? ''}
          panelSize={size}
          moved={Object.keys(moves).flatMap((id) => (known.has(id) ? [layer(known.get(id) as Mask)] : []))}
          selected={selected}
          busy={editor.selecting}
          onPick={(point, preview) => void actions.select(point, preview, { masks: panel.masks, panel: size })}
          onSelectMask={selectMask}
          onMove={(m, move) => void layers.save(m.id, move)}
        />
      }
      editBox={
        <EditBox
          value={editor.instruction}
          selectedLabel={editor.selection?.mask.label ?? null}
          dictation={editor.dictation}
          sending={editor.sending}
          disabled={phase.kind === 'drawing' || phase.kind === 'queued'}
          onChange={(text) => editor.set({ instruction: text })}
          onSubmit={() => void actions.sendEdit()}
          onMicDown={() => void dictation.start()}
          onMicUp={() => void dictation.stop()}
        />
      }
      onClose={close}
      onSelectMask={selectMask}
      onResetMoves={() => void layers.resetAll(Object.keys(moves))}
      onToggleBefore={() => editor.set({ showBefore: !editor.showBefore })}
      onDrawFinal={() => void actions.drawFinal()}
    />
  )
}
