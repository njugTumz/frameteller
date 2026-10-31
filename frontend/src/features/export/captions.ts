import { LANGUAGES } from '../../shared/languages'

/** Burn the captions into the picture, and which language they are in (null: as spoken). */
export interface AnimaticChoice {
  subtitles: boolean
  captionLanguage: string | null
}

/** Languages the captions can be translated into by Muse Spark, all burned in with their own fonts. */
export const CAPTION_LANGUAGES = LANGUAGES.map(({ locale, name }) => ({ locale, name }))
