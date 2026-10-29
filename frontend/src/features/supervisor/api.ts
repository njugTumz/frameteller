import { api, call } from '../../shared/api/client'
import type { Project, Ticket } from '../../shared/api/types'

/** "Apply suggested fix" on a panel: the supervisor's appearance edit on the current render. */
export function applyPanelFix(projectId: string, n: number): Promise<Ticket> {
  return call(() => api.POST('/projects/{project_id}/shots/{n}/panel/review/apply', { params: { path: { project_id: projectId, n } } }))
}

/** "Accept anyway": keep the flagged panel as it is. */
export function acceptPanel(projectId: string, n: number): Promise<Project> {
  return call(() => api.POST('/projects/{project_id}/shots/{n}/panel/review/accept', { params: { path: { project_id: projectId, n } } }))
}

/** "Apply fix" on a flagged reference sheet: redraw it with the supervisor's correction. */
export function applySheetFix(projectId: string, characterId: string): Promise<Ticket> {
  return call(() =>
    api.POST('/projects/{project_id}/cast/{character_id}/review/apply', { params: { path: { project_id: projectId, character_id: characterId } } }),
  )
}

export function acceptSheet(projectId: string, characterId: string): Promise<Project> {
  return call(() =>
    api.POST('/projects/{project_id}/cast/{character_id}/review/accept', { params: { path: { project_id: projectId, character_id: characterId } } }),
  )
}

export function setContinuityChecks(projectId: string, enabled: boolean): Promise<Project> {
  return call(() => api.PATCH('/projects/{project_id}', { params: { path: { project_id: projectId } }, body: { continuity_checks: enabled } }))
}
