import { useCallback, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Project, Shot } from '../../../shared/api/types'
import { useStoryboardStore } from '../../storyboard/store'
import { acceptPanel, acceptSheet, applyPanelFix, applySheetFix, setContinuityChecks } from '../api'

/**
 * The buttons on the supervisor's badges. A fix is an ordinary edit or redraw job: the studio follows it like any
 * other (job.updated, then the project), and the supervisor reviews the result again.
 */
export function useSupervisorActions(projectId: string, onProject: (p: Project) => void) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  /** Run one action; false when it failed (the error is shown). */
  const run = useCallback(async (what: string, action: () => Promise<void>): Promise<boolean> => {
    setBusy(what)
    setError(null)
    try {
      await action()
      return true
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not work. Try again.')
      return false
    } finally {
      setBusy(null)
    }
  }, [])

  const applyFix = useCallback(
    (shot: Shot) =>
      run(`fix:${shot.id}`, async () => {
        const ticket = await applyPanelFix(projectId, shot.number)
        useStoryboardStore.getState().jobStarted(shot.id, { kind: 'edit_panel', status: 'queued', revision: ticket.revision, message: null, key: ticket.key })
      }),
    [projectId, run],
  )
  const accept = useCallback((shot: Shot) => run(`accept:${shot.id}`, async () => onProject(await acceptPanel(projectId, shot.number))), [projectId, onProject, run])
  const fixSheet = useCallback(
    (characterId: string) =>
      run(`fix:${characterId}`, async () => {
        await applySheetFix(projectId, characterId)
      }),
    [projectId, run],
  )
  const acceptSheetAnyway = useCallback(
    (characterId: string) => run(`accept:${characterId}`, async () => onProject(await acceptSheet(projectId, characterId))),
    [projectId, onProject, run],
  )
  const toggle = useCallback(
    (enabled: boolean) => run('toggle', async () => onProject(await setContinuityChecks(projectId, enabled))),
    [projectId, onProject, run],
  )
  return { busy, error, applyFix, accept, fixSheet, acceptSheet: acceptSheetAnyway, toggle }
}
