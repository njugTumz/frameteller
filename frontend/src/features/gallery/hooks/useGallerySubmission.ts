import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { GalleryAudio, MyGalleryEntry } from '../../../shared/api/types'
import { myEntry, submitToGallery, withdrawEntry } from '../api'

const CHECK_EVERY_MS = 4000
const message = (e: unknown) => (e instanceof ApiError ? e.message : 'The studio did not answer. Try again.')

/** This project's gallery entry: submit, follow the check while it runs, withdraw. */
export function useGallerySubmission(projectId: string) {
  const [entry, setEntry] = useState<MyGalleryEntry | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    myEntry(projectId)
      .then((e) => live && setEntry(e))
      .catch(() => undefined) // no entry yet is the usual case
    return () => {
      live = false
    }
  }, [projectId])

  const checking = entry?.status === 'checking'
  useEffect(() => {
    if (!checking) return
    const timer = setInterval(() => {
      myEntry(projectId)
        .then(setEntry)
        .catch(() => undefined)
    }, CHECK_EVERY_MS)
    return () => clearInterval(timer)
  }, [projectId, checking])

  const submit = useCallback(
    async (audio: GalleryAudio) => {
      setBusy(true)
      setError(null)
      try {
        setEntry(await submitToGallery(projectId, audio))
      } catch (e) {
        setError(message(e))
      } finally {
        setBusy(false)
      }
    },
    [projectId],
  )

  const withdraw = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      await withdrawEntry(projectId)
      setEntry(null)
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(false)
    }
  }, [projectId])

  return { entry, busy, error, submit, withdraw }
}
