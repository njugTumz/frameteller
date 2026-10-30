import { api, call } from '../../shared/api/client'
import type { Countries, GalleryAudio, GalleryPage, MyGalleryEntry, PanelStyle } from '../../shared/api/types'
import type { Signature } from '../../shared/creator'

export type GalleryView = 'featured' | 'newest'

/** One view of the gallery, plus the creator countries across all of it (the counter and the filter). */
export function listGallery(view: GalleryView, style: PanelStyle | null, country: string | null): Promise<GalleryPage> {
  return call(() => api.GET('/gallery', { params: { query: { view, style: style ?? undefined, country: country ?? undefined } } }))
}

/** Every country a creator may choose, and one guessed from the browser to offer (never to publish unasked). */
export function listCountries(): Promise<Countries> {
  return call(() => api.GET('/gallery/countries'))
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

export function submitToGallery(projectId: string, audio: GalleryAudio, signature: Signature): Promise<MyGalleryEntry> {
  return call(() => api.POST('/projects/{project_id}/gallery', { params: { path: { project_id: projectId } }, body: { consent: true, audio, ...signature } }))
}

/** Change or remove the name and country. A new name is checked again before it shows. */
export function signEntry(projectId: string, signature: Signature): Promise<MyGalleryEntry> {
  return call(() => api.PATCH('/projects/{project_id}/gallery', { params: { path: { project_id: projectId } }, body: signature }))
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
