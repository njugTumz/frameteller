import { api, call } from '../../shared/api/client'
import type { GalleryAudio, GalleryCard, MyGalleryEntry, PanelStyle } from '../../shared/api/types'

export type GalleryView = 'featured' | 'newest'

export async function listGallery(view: GalleryView, style: PanelStyle | null): Promise<GalleryCard[]> {
  const page = await call(() => api.GET('/gallery', { params: { query: { view, style: style ?? undefined } } }))
  return page.entries
}

/** One heart per browser: a second one changes nothing. */
export function heartEntry(entryId: string) {
  return call(() => api.POST('/gallery/{entry_id}/heart', { params: { path: { entry_id: entryId } } }))
}

export async function reportEntry(entryId: string, reason: string): Promise<void> {
  await call(async () => {
    const result = await api.POST('/gallery/{entry_id}/report', { params: { path: { entry_id: entryId } }, body: { reason } })
    return { ...result, data: result.response.ok ? null : undefined }
  })
}

export function submitToGallery(projectId: string, audio: GalleryAudio): Promise<MyGalleryEntry> {
  return call(() => api.POST('/projects/{project_id}/gallery', { params: { path: { project_id: projectId } }, body: { consent: true, audio } }))
}

/** The project's entry, or null when it was never submitted (or was withdrawn). */
export async function myEntry(projectId: string): Promise<MyGalleryEntry | null> {
  const result = await api.GET('/projects/{project_id}/gallery', { params: { path: { project_id: projectId } } })
  if (result.response.status === 404) return null
  return call(() => Promise.resolve(result))
}

export async function withdrawEntry(projectId: string): Promise<void> {
  await call(async () => {
    const result = await api.DELETE('/projects/{project_id}/gallery', { params: { path: { project_id: projectId } } })
    return { ...result, data: result.response.ok ? null : undefined }
  })
}
