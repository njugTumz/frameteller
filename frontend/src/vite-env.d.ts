/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The backend's public origin, e.g. https://api.example.com. Not secret: it ships in the bundle. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
