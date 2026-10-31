import type { Page, WebSocketRoute } from '@playwright/test'
import { cutoutSvg, panelSvg, sheetSvg } from '../fixtures'

// One backend faked inside the browser for the phone audit: the start page, a studio (a fresh story to tell,
// or a drawn one to edit, export and share), the share page, the gallery and the admin page.
export const API = 'http://localhost:8000'
const AVA = 'en-US-AvaMultilingualNeural'
type Json = Record<string, unknown>

const english = [{ code: 'en', locale: 'en-US', name: 'English' }]
export const VOICES = {
  available: true,
  default: AVA,
  voices: [
    { name: AVA, display_name: 'Ava', gender: 'Female', accent: 'en-US', languages: english, preview_url: `/voices/${AVA}/preview` },
    { name: 'en-US-BrandonMultilingualNeural', display_name: 'Brandon', gender: 'Male', accent: 'en-US', languages: english, preview_url: '/voices/b/preview' },
  ],
}
const review = { outcome: 'checked', summary: 'Checked', issues: [], fix_instruction: '', model: 'muse-spark-1.3', confidence: 0.9, fixes: 0, rubrics: {} }
const LINA = { id: 'lina', name: 'Lina', description: 'a ten-year-old girl with curly black hair and a yellow raincoat', reference_url: '/media/projects/p1/characters/lina/reference', review }
const coat = { id: 'object:coat', label: 'yellow raincoat', character_id: null, box: { left: 850, top: 600, right: 1150, bottom: 930 }, cutout_url: '/media/projects/p1/m/coat.png' }
const panel = (n: number, over: Json = {}) => ({
  revision: 1,
  shown_revision: 1,
  status: 'ready',
  image_url: `/media/projects/p1/panels/s${n}/r1/image`,
  base_image_url: `/media/projects/p1/panels/s${n}/r1/image`,
  width: 1920,
  height: 1280,
  masks: [],
  layers: [],
  outdated: false,
  review,
  versions: [],
  suggested_change: null,
  ...over,
})
const shot = (n: number, p: Json | null = null): Json => ({
  id: `s${n}`,
  number: n,
  framing: n === 1 ? 'wide' : 'close_up',
  character_ids: ['lina'],
  setting: 'a rooftop garden at sunset',
  action: n === 1 ? 'Lina waters tomato plants on the roof.' : 'A paper kite lands in the tomatoes.',
  dialogue: '',
  duration_ms: 2400,
  source_turn_ids: [`t${n}`],
  episode: 1,
  panel: p,
})
const card = { id: 'g1', title: 'The Rooftop Garden', style: 'pencil', episodes: 1, shots: 2, duration_ms: 4800, cover_url: '/gallery/g1/cover.webp', video_url: '/gallery/g1/video.mp4', share_url: 'http://localhost:4173/s/tok', hearts: 3, hearted: false, featured: true, published_at: '2026-10-31T06:00:00Z', creator: { name: 'Captain Biscuit', country: 'KE', official: false } }
const SCRIPT = ['A busy city at sunset.', 'Lina waters tomato plants.']

export interface PhoneBackend {
  posted: { method: string; path: string; body: Json | null }[]
  frames: number
  starts: Json[]
  ws: WebSocketRoute | null
}

/** `drawn`: an approved cast and two drawn panels (edit, export, share). Otherwise a fresh story to tell. */
export async function phoneBackend(page: Page, { drawn = false } = {}): Promise<PhoneBackend> {
  const state = {
    posted: [] as PhoneBackend['posted'],
    frames: 0,
    starts: [] as Json[],
    ws: null as WebSocketRoute | null,
    cast: drawn ? 'approved' : 'draft',
    characters: drawn ? [LINA] : ([] as Json[]),
    shots: drawn ? [shot(1, panel(1)), shot(2, panel(2))] : ([] as Json[]),
    animatic: null as Json | null,
    shareToken: drawn ? 'tok' : (null as string | null),
  }
  const send = (e: Json) => state.ws?.send(JSON.stringify(e))
  const project = () => ({
    id: 'p1',
    title: 'The Rooftop Garden',
    style: 'pencil',
    cast: { status: state.cast, characters: state.characters },
    turns: [],
    shots: state.shots,
    narrations: drawn ? [{ session: 't', duration_ms: 4800, url: '/media/projects/p1/narration/t.wav' }] : [],
    animatic: state.animatic,
    share_token: state.shareToken,
    share_public: false,
    continuity_checks: false,
    supervisor: [],
  })

  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()
    let body: Json | null = null
    try {
      body = method === 'GET' ? null : ((req.postDataJSON?.() as Json | null) ?? null)
    } catch {
      body = null
    }
    if (method !== 'GET') state.posted.push({ method, path, body })
    const json = (status: number, b: unknown) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(b) })
    if (path === '/healthz') return json(200, { status: 'ok' })
    if (path === '/status') return json(200, { open: true, paused: false, full: false, message: null, limits: {} })
    if (path === '/voices') return json(200, VOICES)
    if (path === '/projects' && method === 'POST') return json(201, project())
    if (path === '/projects/p1') return json(200, project())
    if (path === '/projects/p1/cast/approve') {
      state.cast = 'approved'
      return json(200, { approved: true, redrawing: [], job_key: null })
    }
    const render = /^\/projects\/p1\/shots\/(\d+)\/panel$/.exec(path)
    if (render) {
      const n = Number(render[1])
      const revision = drawn || (state.shots[n - 1]?.panel ?? null) ? 2 : 1
      setTimeout(() => {
        state.shots = state.shots.map((s) => (s.number === n ? shot(n, panel(n, { revision, shown_revision: revision })) : s))
        send({ type: 'job.updated', kind: 'generate_panel', key: `k${n}`, status: 'succeeded', shot_id: `s${n}`, revision, message: null })
      }, 400)
      return json(202, { kind: 'generate_panel', key: `k${n}`, enqueued: true, shot_id: `s${n}`, revision })
    }
    if (path.startsWith('/projects/p1/jobs/')) return json(200, { key: path.split('/').at(-1), status: 'succeeded', message: null })
    if (path.endsWith('/panel/select')) return json(200, { cached: false, mask: coat })
    if (path === '/projects/p1/shots/1/panel/layers') {
      setTimeout(() => send({ type: 'job.updated', kind: 'compose_panel', key: 'c1', status: 'succeeded', shot_id: 's1', revision: 1, message: null, progress: null }), 300)
      return json(202, { kind: 'compose_panel', key: 'c1', enqueued: true, shot_id: 's1', revision: 1 })
    }
    if (path === '/projects/p1/exports/animatic') {
      setTimeout(() => {
        state.animatic = { url: '/media/projects/p1/exports/animatic-1.mp4', duration_ms: 4800, subtitles: true, voiced: true, caption_language: '' }
        send({ type: 'job.updated', kind: 'export_animatic', key: 'e1', status: 'succeeded', shot_id: null, revision: null, message: null, progress: null })
      }, 600)
      return json(202, { kind: 'export_animatic', key: 'e1', enqueued: true, shot_id: null, revision: null })
    }
    if (path === '/projects/p1/share' && method === 'POST') {
      state.shareToken = 'tok'
      return json(200, { token: 'tok', public: false, url: `${API}/s/tok`, page_url: 'http://localhost:4173/s/tok' })
    }
    if (path === '/projects/p1/gallery') return json(404, { error: { code: 'not_found', message: 'Not in the gallery' } })
    if (path === '/gallery/countries') return json(200, { codes: ['AE', 'JP', 'KE'], suggested: 'KE' })
    if (path === '/gallery') return json(200, { entries: [card, { ...card, id: 'g2', title: 'The Night Baker', featured: false, creator: { name: '', country: '', official: true } }], countries: [{ code: 'KE', entries: 1 }] })
    if (/^\/gallery\/g\d\/(heart|report)$/.test(path)) return json(200, { hearts: 4, hearted: true })
    if (path === '/shares/tok')
      return json(200, {
        title: 'The Rooftop Garden',
        style: 'pencil',
        shots: [1, 2].map((n) => ({ number: n, framing: 'wide', action: (shot(n).action as string), dialogue: n === 2 ? 'Is that yours?' : '', duration_ms: 2400, image_url: `/shares/tok/panels/${n}` })),
        animatic: { url: '/shares/tok/animatic', duration_ms: 4800 },
        public: true,
        narrated_by: null,
        creator: { name: 'Captain Biscuit', country: 'KE', official: false },
      })
    if (path.startsWith('/admin/')) return adminRoute(path, json)
    if (path.endsWith('.mp4') || path.endsWith('/animatic') || path.endsWith('.wav') || path.includes('/preview'))
      return route.fulfill({ status: 200, contentType: path.endsWith('.wav') || path.includes('/preview') ? 'audio/wav' : 'video/mp4', body: '' })
    if (path.startsWith('/media/') || path.startsWith('/shares/') || path.startsWith('/gallery/')) {
      const svg = path.includes('/characters/') ? sheetSvg('Lina') : path.endsWith('coat.png') ? cutoutSvg : panelSvg(Number(/(?:s|panels\/)(\d+)/.exec(path)?.[1] ?? 1))
      return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: svg })
    }
    return json(404, { error: { code: 'not_mocked', message: path } })
  })

  await page.routeWebSocket(/\/ws\/projects\/p1\/session$/, (ws) => {
    state.ws = ws
    let beats = 0
    const beat = (text: string, extra: Json = {}) => {
      beats += 1
      const n = beats
      send({ type: 'turn.completed', turn: { id: `t${n}`, text, start_ms: (n - 1) * 2400, end_ms: n * 2400, speaker: null, episode: 1, ...extra } })
      state.shots = [...state.shots, shot(n)]
      send({ type: 'shot.created', shot: shot(n) })
      if (n === 1) {
        state.characters = [LINA]
        setTimeout(() => send({ type: 'cast.proposed', characters: [LINA] }), 200)
      }
    }
    ws.onMessage((message) => {
      if (typeof message !== 'string') {
        state.frames += 1
        return
      }
      const m = JSON.parse(message) as Json
      if ('mode' in m) {
        state.starts.push(m)
        send({ type: 'session.started', mode: m.mode })
        if (m.mode === 'read' || m.mode === 'teleprompter') {
          send({ type: 'script.accepted', episodes: [{ number: 1, paragraphs: SCRIPT.map((t) => ({ narration: t, direction: t })) }] })
        }
        if (m.mode === 'read') {
          SCRIPT.forEach((text, i) => {
            send({ type: 'script.voiced', paragraph: i, episode: 1, text, original: text, audio_url: `/media/projects/p1/speech/${i}.wav`, duration_ms: 400 })
            beat(text, { direction: text })
          })
          setTimeout(() => send({ type: 'session.ended', turns: 2, shots: 2 }), 300)
        }
      }
      if (m.type === 'beat') beat(beats === 0 ? 'Scene one. A rooftop garden at sunset.' : 'A paper kite lands in the tomatoes.')
      if (m.type === 'end') send({ type: 'session.ended', turns: beats, shots: beats, heard: true })
    })
  })
  return state
}

const OVERVIEW = {
  paused: false,
  budgets: [{ lane: 'public', day: '2026-10-31', cap_usd: 20, spent_usd: 3.21, left_usd: 16.79 }],
  gates: [{ name: 'image', limit: 4, in_flight: 1, waiting: 0, hold_s: 0, longest_wait_s: 0, max_waiting: 20 }],
  live_sessions: 1,
  read_it_to_me: true,
  judge_pass: true,
  glimmer_warm_until: null,
  judge_reserve: { calendar_usd: 30, override_usd: null, stories_per_pass_per_day: 5 },
  judge_passes: [{ pass_id: 'pass-a1', first_seen: '2026-10-31T05:00:00Z', stories_today: 2, spent_today_usd: 0.4 }],
  judge_glimmer: null,
}
const ENTRY = { id: 'g1', project_id: 'p1', title: 'The Rooftop Garden', style: 'pencil', status: 'pending', note: '', reviewed_by: '', audio: 'none', featured: false, hearts: 3, reports: [{ reason: 'spam', at: '2026-10-31T05:00:00Z' }], submitted_at: '2026-10-31T05:00:00Z', published_at: null, share_token: 'tok', has_video: true, creator: { name: 'Captain Biscuit', country: 'KE', official: false } }
const ERRORS = {
  recent: [{ at: '2026-10-31T05:00:00Z', component: 'image', code: 'timeout', message: 'Muse Image took too long.', project_id: 'p1', visitor: 'v-1' }],
  counts_24h: { image: 1 },
  health: [{ model: 'muse-image-1.0', calls: 41, failures: 0, retries: 1, p95_ms: 26000 }],
  failed_jobs: [{ key: 'generate_panel:p1:s1:r2', kind: 'generate_panel', component: 'image', code: 'timeout', message: 'Muse Image took too long.', at: '2026-10-31T05:00:00Z', project_id: 'p1', retries: 0 }],
  reports: [{ id: 'r1', at: '2026-10-31T05:00:00Z', project_id: 'p1', text: 'The cat changed colour in shot 3.', visitor: 'v-1' }],
}
function adminRoute(path: string, json: (status: number, b: unknown) => Promise<void>) {
  if (path === '/admin/overview') return json(200, OVERVIEW)
  if (path === '/admin/gallery') return json(200, [ENTRY])
  if (path === '/admin/errors') return json(200, ERRORS)
  return json(200, ENTRY)
}
