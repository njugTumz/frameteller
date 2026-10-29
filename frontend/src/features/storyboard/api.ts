import { api, call } from '../../shared/api/client'
import type { JobStatusReport, Project, Ticket } from '../../shared/api/types'

export function getProject(projectId: string, signal?: AbortSignal): Promise<Project> {
  return call(() => api.GET('/projects/{project_id}', { params: { path: { project_id: projectId } }, signal }))
}

/** One job's status: the fallback when its job.updated events were missed (a dropped socket, a new revision). */
export function getJobStatus(projectId: string, key: string, signal?: AbortSignal): Promise<JobStatusReport> {
  return call(() => api.GET('/projects/{project_id}/jobs/{key}', { params: { path: { project_id: projectId, key } }, signal }))
}

/** Queue the next revision of shot n's panel. Shots are addressed by number (docs/api-events.md). */
export function renderPanel(projectId: string, n: number, quality: 'draft' | 'final'): Promise<Ticket> {
  return call(() => api.POST('/projects/{project_id}/shots/{n}/panel', { params: { path: { project_id: projectId, n } }, body: { quality } }))
}
