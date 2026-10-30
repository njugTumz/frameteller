import { api, call } from '../../shared/api/client'
import type { Project } from '../../shared/api/types'

const project = (projectId: string) => ({ project_id: projectId })

/** Remove a beat: its words, the shots made only from it, and its stretch of voice in the animatic. */
export function removeBeat(projectId: string, turnId: string): Promise<Project> {
  return call(() => api.DELETE('/projects/{project_id}/turns/{turn_id}', { params: { path: { ...project(projectId), turn_id: turnId } } }))
}

/** Join a beat with the one before or after it. */
export function mergeBeats(projectId: string, turnId: string, other: 'previous' | 'next'): Promise<Project> {
  return call(() =>
    api.POST('/projects/{project_id}/turns/{turn_id}/merge', { params: { path: { ...project(projectId), turn_id: turnId } }, body: { other } }),
  )
}

/** Delete one shot and its panel (by id: numbers change as shots go). */
export function deleteShot(projectId: string, shotId: string): Promise<Project> {
  return call(() => api.DELETE('/projects/{project_id}/shots/{shot_id}', { params: { path: { ...project(projectId), shot_id: shotId } } }))
}
