import { API_BASE_URL } from '../../config'
import { api, call } from '../../shared/api/client'
import type { Voice, Voices } from '../../shared/api/types'

export type { Voice, Voices }

/** The voices "Read it to me" offers. `available` is false when the studio has no Text-to-Speech. */
export function fetchVoices(): Promise<Voices> {
  return call(() => api.GET('/voices'))
}

/** A short sentence in the voice and language: a plain URL, so an <audio> element plays it. */
export function previewUrl(voice: Voice, language: string): string {
  return `${API_BASE_URL}${voice.preview_url}?language=${encodeURIComponent(language)}`
}
