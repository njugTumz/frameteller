import { useCallback } from 'react'
import { StartScreen } from '../../features/start/components/StartScreen'
import { useStartStory } from '../../features/start/hooks/useStartStory'
import { useStartStore } from '../../features/start/store'
import { useBackendWake } from '../../shared/hooks/useBackendWake'
import { WakeNotice } from '../../shared/ui/WakeNotice'
import { navigate, studioPath } from '../router'

export function StartPage() {
  const { title, style, names, keepAudio, creating, error, setTitle, setStyle, setNames, setKeepAudio } = useStartStore()
  const { wake, retry } = useBackendWake()
  const start = useStartStory(useCallback((id: string) => navigate(studioPath(id)), []))
  return (
    <StartScreen
      form={{ title, style, names, keepAudio }}
      creating={creating}
      error={error}
      wakeNotice={<WakeNotice wake={wake} onRetry={retry} />}
      onChange={(patch) => {
        if (patch.title !== undefined) setTitle(patch.title)
        if (patch.style !== undefined) setStyle(patch.style)
        if (patch.names !== undefined) setNames(patch.names)
        if (patch.keepAudio !== undefined) setKeepAudio(patch.keepAudio)
      }}
      onSubmit={() => void start()}
    />
  )
}
