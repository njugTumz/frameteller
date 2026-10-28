/** App-wide configuration. Rename the product here (and in marketing/index.html CONFIG). */
export const APP_NAME = 'Frameteller'

/** Never put a secret in a VITE_* variable: Vite bakes them into the public bundle (CLAUDE.md section 8). */
export function apiBaseUrl(configured = import.meta.env.VITE_API_BASE_URL): string {
  const base = configured?.trim() || 'http://localhost:8000'
  return base.replace(/\/+$/, '')
}

export const API_BASE_URL = apiBaseUrl()

/** The WebSocket origin that matches the API origin: http → ws, https → wss. */
export function wsBaseUrl(base = API_BASE_URL): string {
  return base.replace(/^http/, 'ws')
}
