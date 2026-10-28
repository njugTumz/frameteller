import { existsSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'
import { writePadded } from './narration'
import { liveWav, sourceWav } from '../playwright.config'

/** Live run only: the fake microphone plays the narration with silence in front (see e2e/narration.ts). */
export default function setup(): void {
  if (!existsSync(sourceWav)) return // the spec skips itself
  mkdirSync(dirname(liveWav), { recursive: true })
  writePadded(sourceWav, liveWav)
}
