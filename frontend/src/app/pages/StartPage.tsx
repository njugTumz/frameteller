import { useCallback, useState } from 'react'
import { StartScreen } from '../../features/start/components/StartScreen'
import { FirstVisitGuide } from '../../features/start/components/FirstVisitGuide'
import { TourOffer } from '../../features/tour/components/TourOffer'
import { tourSeen, useTourStore } from '../../features/tour/store'
import { startTour } from '../tour/start'
import { useFirstVisit } from '../../features/start/hooks/useFirstVisit'
import { useSampleStory, useStartStory } from '../../features/start/hooks/useStartStory'
import { useStartStore } from '../../features/start/store'
import { useVoicePreview } from '../../features/script/hooks/useVoicePreview'
import { useVoices } from '../../features/script/hooks/useVoices'
import { useBackendWake } from '../../shared/hooks/useBackendWake'
import { useStudioStatus } from '../../shared/status/store'
import { WakeNotice } from '../../shared/ui/WakeNotice'
import { navigate, studioPath } from '../router'

export function StartPage() {
  const { title, style, names, keepAudio, mode, script, format, voice, language, speaking, creating, error, setTitle, setStyle, setNames, setKeepAudio, set } =
    useStartStore()
  const voices = useVoices()
  const preview = useVoicePreview()
  const { wake, retry } = useBackendWake()
  const full = useStudioStatus((s) => s.full)
  const open = useCallback((id: string) => navigate(studioPath(id)), [])
  const start = useStartStory(open)
  const sample = useSampleStory(open)
  const guide = useFirstVisit()
  const tour = useTourStore()
  const [seenTour] = useState(tourSeen)
  // The tour replaces the three-step guide; the guide stays as the fallback if the tour cannot load.
  const intro = tour.failed
    ? guide.show && <FirstVisitGuide onDismiss={guide.dismiss} />
    : !seenTour && !tour.declined && tour.status === 'off' && voices.available && <TourOffer onTake={startTour} onDismiss={tour.decline} />
  return (
    <StartScreen
      form={{ title, style, names, keepAudio, mode, script, format, voice, language, speaking }}
      voices={voices}
      previewing={preview.previewing}
      onPreview={preview.play}
      creating={creating}
      error={error}
      full={full}
      wakeNotice={<WakeNotice wake={wake} onRetry={retry} />}
      guide={intro || null}
      onChange={(patch) => {
        if (patch.title !== undefined) setTitle(patch.title)
        if (patch.style !== undefined) setStyle(patch.style)
        if (patch.names !== undefined) setNames(patch.names)
        if (patch.keepAudio !== undefined) setKeepAudio(patch.keepAudio)
        const { mode: m, script: t, format: f, voice: v, language: l, speaking: k } = patch
        set(Object.fromEntries(Object.entries({ mode: m, script: t, format: f, voice: v, language: l, speaking: k }).filter(([, x]) => x !== undefined)))
      }}
      onSubmit={() => void start()}
      onSample={voices.available ? () => void sample() : undefined}
    />
  )
}
