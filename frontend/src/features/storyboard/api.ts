import { api, call } from '../../shared/api/client'
import type { Project, Ticket } from '../../shared/api/types'

export function getProject(projectId: string, signal?: AbortSignal): Promise<Project> {
  return call(() => api.GET('/projects/{project_id}', { params: { path: { project_id: projectId } }, signal }))
}

/** Queue the next revision of shot n's panel. Shots are addressed by number (docs/api-events.md). */
export function renderPanel(projectId: string, n: number, quality: 'draft' | 'final'): Promise<Ticket> {
  return call(() => api.POST('/projects/{project_id}/shots/{n}/panel', { params: { path: { project_id: projectId, n } }, body: { quality } }))
}
