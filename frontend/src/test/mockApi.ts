import { vi } from 'vitest'

export interface Call {
  method: string
  path: string
  body: unknown
}

type Handler = (call: Call) => { status?: number; body: unknown } | Promise<{ status?: number; body: unknown }>

/** Stub fetch for the typed client: routes are "METHOD /path" with :params; every call is recorded. */
export function mockApi(routes: Record<string, Handler>): { calls: Call[] } {
  const calls: Call[] = []
  const table = Object.entries(routes).map(([key, handler]) => {
    const [method, pattern] = key.split(' ') as [string, string]
    const re = new RegExp(`^${pattern.replace(/:[a-z_]+/g, '[^/]+')}$`)
    return { method, re, handler }
  })
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init)
    const url = new URL(request.url)
    const text = request.method === 'GET' ? '' : await request.text()
    let body: unknown = text
    try {
      body = text ? JSON.parse(text) : undefined
    } catch {
      // not JSON (audio)
    }
    const call = { method: request.method, path: url.pathname, body }
    calls.push(call)
    const route = table.find((r) => r.method === request.method && r.re.test(url.pathname))
    if (!route) return new Response(JSON.stringify({ error: { code: 'not_mocked', message: `${call.method} ${call.path}` } }), { status: 404 })
    const { status = 200, body: out } = await route.handler(call)
    return new Response(JSON.stringify(out), { status, headers: { 'Content-Type': 'application/json' } })
  })
  return { calls }
}
