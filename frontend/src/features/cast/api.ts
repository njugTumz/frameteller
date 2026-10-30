import { api, call } from '../../shared/api/client'
import type { CastReview, Project, Ticket } from '../../shared/api/types'

/** Approve the cast. Changed descriptions redraw those sheets first: then approved is false and cast.proposed follows. */
export function approveCast(projectId: string, descriptions: Record<string, string>): Promise<CastReview> {
  return call(() => api.POST('/projects/{project_id}/cast/approve', { params: { path: { project_id: projectId } }, body: { descriptions } }))
}

export function regenerateReference(projectId: string, characterId: string): Promise<Ticket> {
  return call(() =>
    api.POST('/projects/{project_id}/cast/{character_id}/regenerate', { params: { path: { project_id: projectId, character_id: characterId } } }),
  )
}

const characterPath = (projectId: string, characterId: string) => ({ params: { path: { project_id: projectId, character_id: characterId } } })

/** "Try again" on one of a character's looks (ADR 0018): its sheet is drawn again from the everyday one. */
export function regenerateLook(projectId: string, characterId: string, lookId: string): Promise<Ticket> {
  return call(() =>
    api.POST('/projects/{project_id}/cast/{character_id}/looks/{look_id}/regenerate', {
      params: { path: { project_id: projectId, character_id: characterId, look_id: lookId } },
    }),
  )
}

export function renameCharacter(projectId: string, characterId: string, name: string): Promise<Project> {
  return call(() => api.PATCH('/projects/{project_id}/cast/{character_id}', { ...characterPath(projectId, characterId), body: { name } }))
}

/** Shots keep their action and lose the character. */
export function removeCharacter(projectId: string, characterId: string): Promise<Project> {
  return call(() => api.DELETE('/projects/{project_id}/cast/{character_id}', characterPath(projectId, characterId)))
}

/** Every shot of `characterId` shows `into` instead; their panels are redrawn as drafts. */
export function mergeCharacter(projectId: string, characterId: string, into: string): Promise<Project> {
  return call(() => api.POST('/projects/{project_id}/cast/{character_id}/merge', { ...characterPath(projectId, characterId), body: { into } }))
}
