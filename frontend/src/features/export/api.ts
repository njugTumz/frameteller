import { API_BASE_URL } from '../../config'
import { api, call } from '../../shared/api/client'
import type { Project, ShareLink, Ticket } from '../../shared/api/types'

/** Queue the MP4 animatic. Progress arrives as job.updated (export_animatic). */
export function exportAnimatic(projectId: string, subtitles: boolean): Promise<Ticket> {
  return call(() => api.POST('/projects/{project_id}/exports/animatic', { params: { path: { project_id: projectId } }, body: { subtitles } }))
}

/** The storyboard sheet: a plain link, so the browser downloads it. */
export function storyboardPdfUrl(projectId: string): string {
  return `${API_BASE_URL}/projects/${encodeURIComponent(projectId)}/exports/storyboard.pdf`
}

/** Turn the link on, or change whether search engines may index it. The link itself never changes. */
export function createShare(projectId: string, isPublic = false): Promise<ShareLink> {
  return call(() => api.POST('/projects/{project_id}/share', { params: { path: { project_id: projectId } }, body: { public: isPublic } }))
}

export async function revokeShare(projectId: string): Promise<void> {
  await call(async () => {
    const result = await api.DELETE('/projects/{project_id}/share', { params: { path: { project_id: projectId } } })
    return { ...result, data: result.response.ok ? null : undefined }
  })
}

/** "Delete my recording": every kept narration of the project. The animatic is then silent. */
export function deleteNarration(projectId: string): Promise<Project> {
  return call(() => api.DELETE('/projects/{project_id}/narration', { params: { path: { project_id: projectId } } }))
}

/** The link to post: the API's stub that previews on X and sends browsers to the share page. */
export function shareUrl(token: string): string {
  return `${API_BASE_URL}/s/${encodeURIComponent(token)}`
}
