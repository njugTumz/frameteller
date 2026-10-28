import { API_BASE_URL } from '../../config'
import { api, call } from '../../shared/api/client'
import type { SharedProject } from '../../shared/api/types'

export function getShared(token: string, signal?: AbortSignal): Promise<SharedProject> {
  return call(() => api.GET('/shares/{token}', { params: { path: { token } }, signal }))
}

/** Share media URLs are API paths ("/shares/{token}/..."). */
export function sharedUrl(path: string | null | undefined): string | null {
  return path ? `${API_BASE_URL}${path}` : null
}
