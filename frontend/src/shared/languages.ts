/** The nine languages Frameteller speaks: narration, captions and the Read it to me voices. Each in its own name. */
export const LANGUAGES = [
  { code: 'en', locale: 'en-US', name: 'English' },
  { code: 'fr', locale: 'fr-FR', name: 'Français' },
  { code: 'es', locale: 'es-ES', name: 'Español' },
  { code: 'pt', locale: 'pt-BR', name: 'Português' },
  { code: 'hi', locale: 'hi-IN', name: 'हिन्दी' },
  { code: 'ar', locale: 'ar-SA', name: 'العربية' },
  { code: 'ja', locale: 'ja-JP', name: '日本語' },
  { code: 'ko', locale: 'ko-KR', name: '한국어' },
  { code: 'zh', locale: 'zh-CN', name: '中文' },
] as const

/** A locale we speak, or '' (auto-detect) for anything else. */
export const speakingLanguage = (value: unknown): string =>
  typeof value === 'string' && LANGUAGES.some((l) => l.locale === value) ? value : ''
