import createClient from 'openapi-fetch'
import { API_BASE_URL } from '../../config'
import type { paths } from './schema'

/** The typed REST client, generated from backend/openapi.json. The browser only ever talks to our backend. */
// fetch is looked up per request (not captured once), so tests and polyfills can replace it.
export const api = createClient<paths>({ baseUrl: API_BASE_URL, fetch: (request) => globalThis.fetch(request) })

/** A failed request, with a message written for the user (the backend's ErrorOut, or ours). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

const FALLBACK: Record<number, string> = {
  402: 'This project has reached its spending limit for today.',
  404: 'We could not find that. It may have been removed.',
  409: 'Something else changed this at the same moment. Try again.',
  413: 'That is too large to send.',
  422: 'The studio could not read that request.',
  429: 'That was a lot at once. Wait a few seconds and try again.',
}

function messageOf(error: unknown): { code?: string; message?: string } {
  if (error && typeof error === 'object' && 'error' in error) {
    const body = (error as { error?: unknown }).error
    if (body && typeof body === 'object') {
      const { code, message } = body as { code?: unknown; message?: unknown }
      return { code: typeof code === 'string' ? code : undefined, message: typeof message === 'string' ? message : undefined }
    }
  }
  return {}
}

/** Turn an openapi-fetch result into its data, or throw an ApiError the UI can show as is. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data !== undefined && result.response.ok) return result.data
  const status = result.response.status
  const { code, message } = messageOf(result.error)
  throw new ApiError(status, code ?? `http_${status}`, message ?? FALLBACK[status] ?? 'The studio did not answer properly. Try again.')
}

/** Network failures (offline, CORS, a sleeping backend) become an ApiError with status 0. */
export async function call<T>(request: () => Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let result
  try {
    result = await request()
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'unreachable', 'The studio is not answering. Check your connection, then try again.')
  }
  return unwrap(result)
}

/** Media keys come back as "/media/..." paths on the backend. */
export function mediaUrl(path: string | null | undefined): string | null {
  return path ? `${API_BASE_URL}${path}` : null
}
