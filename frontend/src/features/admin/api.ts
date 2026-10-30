import { API_BASE_URL } from '../../config'
import { ApiError } from '../../shared/api/client'

/** The operator's API (not in the public schema): every call carries the admin token as a bearer token. */

export interface Budget {
  lane: string
  day: string
  cap_usd: number
  spent_usd: number
  left_usd: number
}

export interface GateState {
  name: string
  limit: number
  in_flight: number
  waiting: number
  hold_s: number
  longest_wait_s: number
  max_waiting: number
}

export interface Overview {
  paused: boolean
  budgets: Budget[]
  gates: GateState[]
  live_sessions: number
  read_it_to_me: boolean
  judge_pass: boolean
  glimmer_warm_until: string | null
  judge_reserve: JudgeReserve
  judge_passes: JudgePass[]
}

export interface JudgeReserve {
  calendar_usd: number
  override_usd: number | null
  stories_per_pass_per_day: number
}

export interface JudgePass {
  pass_id: string
  first_seen: string
  stories_today: number
  spent_today_usd: number
}

export interface AdminEntry {
  id: string
  project_id: string
  title: string
  style: string
  status: string
  note: string
  reviewed_by: string
  audio: string
  featured: boolean
  hearts: number
  reports: { reason: string; at: string }[]
  submitted_at: string
  published_at: string | null
  share_token: string
  has_video: boolean
}

export type AdminAction = 'publish' | 'hide' | 'feature' | 'unfeature'

/** One recorded error: our own words, never keys, tokens, audio or IP addresses. */
export interface Incident {
  at: string
  component: string
  code: string
  message: string
  project_id: string | null
  visitor: string | null
}

export interface ModelHealth {
  model: string
  calls: number
  failures: number
  retries: number
  p95_ms: number | null
}

export interface FailedJob {
  key: string
  kind: string
  component: string
  code: string
  message: string
  at: string
  project_id: string | null
  retries: number
}

export interface ProblemReport {
  id: string
  at: string
  project_id: string
  text: string
  visitor: string | null
}

export interface Errors {
  recent: Incident[]
  counts_24h: Record<string, number>
  health: ModelHealth[]
  failed_jobs: FailedJob[]
  reports: ProblemReport[]
}

async function request(token: string, method: string, path: string, body?: unknown): Promise<Response> {
  let response: Response
  try {
    response = await globalThis.fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'unreachable', 'The studio is not answering.')
  }
  if (response.status === 401 || response.status === 404) throw new ApiError(response.status, 'denied', 'This admin link is not valid.')
  if (!response.ok) {
    const error = ((await response.json().catch(() => null)) as { error?: { code: string; message: string } } | null)?.error
    throw new ApiError(response.status, error?.code ?? 'error', error?.message ?? `The studio answered ${response.status}.`)
  }
  return response
}

export const getOverview = (token: string) => request(token, 'GET', '/admin/overview').then((r) => r.json() as Promise<Overview>)
export const getEntries = (token: string) => request(token, 'GET', '/admin/gallery').then((r) => r.json() as Promise<AdminEntry[]>)
export const actOn = (token: string, id: string, action: AdminAction) =>
  request(token, 'POST', `/admin/gallery/${encodeURIComponent(id)}`, { action }).then((r) => r.json() as Promise<AdminEntry>)
export const removeEntry = (token: string, id: string) => request(token, 'DELETE', `/admin/gallery/${encodeURIComponent(id)}`).then(() => undefined)
/** Lower the judges' daily reserve now (null: back to the calendar's). */
export const setJudgeReserve = (token: string, usd: number | null) =>
  request(token, 'PUT', '/admin/judge/reserve', { usd }).then((r) => r.json() as Promise<JudgeReserve>)
export const getErrors = (token: string) => request(token, 'GET', '/admin/errors').then((r) => r.json() as Promise<Errors>)
/** Run a job that gave up again (refused while the studio is paused or full). */
export const retryJob = (token: string, key: string) => request(token, 'POST', '/admin/jobs/retry', { key }).then((r) => r.json() as Promise<FailedJob>)
/** A pending entry's video, fetched with the token, as an object URL for a <video>. */
export const entryVideo = (token: string, id: string) =>
  request(token, 'GET', `/admin/gallery/${encodeURIComponent(id)}/video.mp4`).then(async (r) => URL.createObjectURL(await r.blob()))
