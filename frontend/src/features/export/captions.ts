/** Burn the captions into the picture, and which language they are in (null: as spoken). */
export interface AnimaticChoice {
  subtitles: boolean
  captionLanguage: string | null
}

/** Languages the captions can be translated into by Muse Spark. Hindi and Arabic come as a soft track and .srt. */
export const CAPTION_LANGUAGES = [
  { locale: 'en-US', name: 'English' },
  { locale: 'fr-FR', name: 'Français' },
  { locale: 'es-ES', name: 'Español' },
  { locale: 'pt-BR', name: 'Português' },
  { locale: 'hi-IN', name: 'हिन्दी' },
  { locale: 'ar-SA', name: 'العربية' },
] as const
