import { api, call } from '../../shared/api/client'
import type { CastReview, Ticket } from '../../shared/api/types'

/** Approve the cast. Changed descriptions redraw those sheets first: then approved is false and cast.proposed follows. */
export function approveCast(projectId: string, descriptions: Record<string, string>): Promise<CastReview> {
  return call(() => api.POST('/projects/{project_id}/cast/approve', { params: { path: { project_id: projectId } }, body: { descriptions } }))
}

export function regenerateReference(projectId: string, characterId: string): Promise<Ticket> {
  return call(() =>
    api.POST('/projects/{project_id}/cast/{character_id}/regenerate', { params: { path: { project_id: projectId, character_id: characterId } } }),
  )
}
