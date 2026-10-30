import { api, call } from '../../shared/api/client'

/** "Report a problem": optional words, sent with this project's id to the admin's Errors tab. */
export function reportProblem(projectId: string, text: string): Promise<{ id: string }> {
  return call(() => api.POST('/projects/{project_id}/problems', { params: { path: { project_id: projectId } }, body: { text } }))
}
