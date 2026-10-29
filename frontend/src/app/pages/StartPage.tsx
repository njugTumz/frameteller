import { useCallback } from 'react'
import { StartScreen } from '../../features/start/components/StartScreen'
import { useStartStory } from '../../features/start/hooks/useStartStory'
import { useStartStore } from '../../features/start/store'
import { useVoicePreview } from '../../features/script/hooks/useVoicePreview'
import { useVoices } from '../../features/script/hooks/useVoices'
import { useBackendWake } from '../../shared/hooks/useBackendWake'
import { useStudioStatus } from '../../shared/status/store'
import { WakeNotice } from '../../shared/ui/WakeNotice'
import { navigate, studioPath } from '../router'

export function StartPage() {
  const { title, style, names, keepAudio, mode, script, format, voice, language, creating, error, setTitle, setStyle, setNames, setKeepAudio, set } =
    useStartStore()
  const voices = useVoices()
  const preview = useVoicePreview()
  const { wake, retry } = useBackendWake()
  const full = useStudioStatus((s) => s.full)
  const start = useStartStory(useCallback((id: string) => navigate(studioPath(id)), []))
  return (
    <StartScreen
      form={{ title, style, names, keepAudio, mode, script, format, voice, language }}
      voices={voices}
      previewing={preview.previewing}
      onPreview={preview.play}
      creating={creating}
      error={error}
      full={full}
      wakeNotice={<WakeNotice wake={wake} onRetry={retry} />}
      onChange={(patch) => {
        if (patch.title !== undefined) setTitle(patch.title)
        if (patch.style !== undefined) setStyle(patch.style)
        if (patch.names !== undefined) setNames(patch.names)
        if (patch.keepAudio !== undefined) setKeepAudio(patch.keepAudio)
        const { mode: m, script: t, format: f, voice: v, language: l } = patch
        set(Object.fromEntries(Object.entries({ mode: m, script: t, format: f, voice: v, language: l }).filter(([, x]) => x !== undefined)))
      }}
      onSubmit={() => void start()}
    />
  )
}
