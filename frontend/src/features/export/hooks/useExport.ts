import { useCallback, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { Project } from '../../../shared/api/types'
import { useStoryboardStore } from '../../storyboard/store'
import { createShare, deleteNarration, exportAnimatic, revokeShare } from '../api'

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'The studio did not answer. Try again.')

/**
 * Exports and sharing for one project. The export runs as a job: its progress lives in the storyboard store
 * (job.updated), and the finished animatic arrives with the next project fetch.
 */
export function useExport(projectId: string, onProject: (p: Project) => void) {
  const [error, setError] = useState<string | null>(null)
  const [sharing, setSharing] = useState(false)

  const animatic = useCallback(
    async (subtitles: boolean) => {
      setError(null)
      useStoryboardStore.getState().set({ exportJob: { status: 'queued', progress: 0, message: null } })
      try {
        const ticket = await exportAnimatic(projectId, subtitles)
        // The same storyboard was already exported: nothing new runs, so fetch it again for the result.
        if (!ticket.enqueued) useStoryboardStore.getState().set({ exportJob: { status: 'succeeded', progress: 1, message: null }, stale: true })
      } catch (e) {
        useStoryboardStore.getState().set({ exportJob: null })
        setError(message(e))
      }
    },
    [projectId],
  )

  /** Create the link, or switch it between unlisted and public. */
  const share = useCallback(async (isPublic: boolean) => {
    setError(null)
    setSharing(true)
    try {
      const link = await createShare(projectId, isPublic)
      useStoryboardStore.getState().set({ shareToken: link.token, sharePublic: link.public })
    } catch (e) {
      setError(message(e))
    } finally {
      setSharing(false)
    }
  }, [projectId])

  const unshare = useCallback(async () => {
    setError(null)
    setSharing(true)
    try {
      await revokeShare(projectId)
      useStoryboardStore.getState().set({ shareToken: null, sharePublic: false })
    } catch (e) {
      setError(message(e))
    } finally {
      setSharing(false)
    }
  }, [projectId])

  const forgetRecording = useCallback(async () => {
    setError(null)
    try {
      onProject(await deleteNarration(projectId))
    } catch (e) {
      setError(message(e))
    }
  }, [projectId, onProject])

  return { animatic, share, unshare, forgetRecording, sharing, error }
}
