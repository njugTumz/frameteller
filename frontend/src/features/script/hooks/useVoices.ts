import { useEffect, useState } from 'react'
import { fetchVoices, type Voices } from '../api'
import { DEFAULT_VOICE } from '../store'

const NONE: Voices = { available: false, default: DEFAULT_VOICE, voices: [] }

/** The voices offered, fetched once per page. Until they arrive (or if the studio is unreachable), none. */
export function useVoices(): Voices {
  const [voices, setVoices] = useState<Voices>(NONE)
  useEffect(() => {
    let live = true
    fetchVoices()
      .then((v) => live && setVoices(v))
      .catch(() => undefined)
    return () => {
      live = false
    }
  }, [])
  return voices
}
