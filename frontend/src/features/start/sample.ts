import type { PanelStyle } from '../../shared/api/types'
import { DEFAULT_VOICE, type TellingChoice } from '../script/store'

/**
 * "Try a sample story": an original script of ours (the team's rooftop story), read aloud by the Ava voice
 * through the real pipeline, so a visitor without a microphone sees the whole flow. It is a normal story: it
 * counts toward the per-visitor caps like any other (judges are exempt, as always).
 */
export const SAMPLE_STORY = {
  title: 'The Rooftop Garden',
  style: 'pencil' as PanelStyle,
  names: 'Lina, Bolt',
  script: `Wide shot. A busy city at sunset. On top of a tall apartment building, there is a small, messy rooftop garden.

Medium shot. Lina, a ten-year-old girl with curly black hair and a yellow raincoat, waters tomato plants with a red watering can.

Close-up. Behind the plants, a small rusty robot named Bolt, with one round blue eye and a dented copper body, is trying to hide.

Lina laughs and offers Bolt a tiny watering can of his own.

Medium shot. Bolt and Lina water the garden together. Bolt's blue eye glows happily.

Wide shot. At night, the city lights twinkle below as Lina and Bolt sit on the edge of the roof, looking up at the stars.`,
}

export const SAMPLE_CHOICE: TellingChoice = {
  mode: 'read',
  script: SAMPLE_STORY.script,
  format: 'text',
  voice: DEFAULT_VOICE,
  language: 'en-US',
  speaking: '',
}
