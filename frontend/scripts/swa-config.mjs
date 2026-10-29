// Writes dist/staticwebapp.config.json for Azure Static Web Apps: SPA fallback and security headers.
// The CSP names the backend origin (REST, the session WebSocket, /media images and the animatic), taken from
// VITE_API_BASE_URL, the same variable the build reads. Run after `npm run build`.
// Also writes dist/robots.txt: with STUDIO_NOINDEX=1 (staging) it disallows everything and every response says
// X-Robots-Tag: noindex; otherwise only share pages (/s/) may be crawled, and each decides with its meta tag.
import { writeFileSync } from 'node:fs'

const base = process.env.VITE_API_BASE_URL
if (!base) {
  console.error('Set VITE_API_BASE_URL to the backend URL, e.g. https://ca-frameteller-staging.<region>.azurecontainerapps.io')
  process.exit(1)
}
const api = new URL(base)
const ws = `${api.protocol === 'https:' ? 'wss:' : 'ws:'}//${api.host}`

const csp = [
  "default-src 'self'",
  "script-src 'self'", // the app bundle and the AudioWorklet module
  "worker-src 'self'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com", // React and Konva set inline styles
  'font-src https://fonts.gstatic.com',
  `img-src 'self' data: blob: ${api.origin}`,
  `connect-src 'self' ${api.origin} ${ws}`,
  `media-src 'self' blob: ${api.origin}`, // the animatic player
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join('; ')

const noindex = process.env.STUDIO_NOINDEX === '1'

const config = {
  navigationFallback: {
    rewrite: '/index.html',
    exclude: ['/assets/*', '/favicon.svg', '/*.{json,txt,png,svg,ico,webp}'],
  },
  routes: [{ route: '/assets/*', headers: { 'Cache-Control': 'public, max-age=31536000, immutable' } }],
  globalHeaders: {
    'Content-Security-Policy': csp,
    'Permissions-Policy': 'microphone=(self), camera=(), geolocation=(), payment=()',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Cross-Origin-Opener-Policy': 'same-origin',
    ...(noindex ? { 'X-Robots-Tag': 'noindex, nofollow' } : {}),
  },
}

writeFileSync('dist/staticwebapp.config.json', `${JSON.stringify(config, null, 2)}\n`)
writeFileSync('dist/robots.txt', noindex ? 'User-agent: *\nDisallow: /\n' : 'User-agent: *\nAllow: /s/\nDisallow: /\n')
console.log(`dist/staticwebapp.config.json: API ${api.origin}, WebSocket ${ws}; robots.txt ${noindex ? 'disallows all' : 'allows /s/'}`)
