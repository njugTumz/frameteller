import { useEffect, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import type { SharedProject } from '../../../shared/api/types'
import { getShared } from '../api'

export type SharedState = { status: 'loading' } | { status: 'ready'; project: SharedProject } | { status: 'gone' } | { status: 'error'; message: string }

/** The read-only storyboard behind a share token. */
export function useShared(token: string): SharedState {
  const [state, setState] = useState<SharedState>({ status: 'loading' })
  useEffect(() => {
    const controller = new AbortController()
    getShared(token, controller.signal)
      .then((project) => setState({ status: 'ready', project }))
      .catch((e: unknown) => {
        if (controller.signal.aborted) return
        if (e instanceof ApiError && e.status === 404) setState({ status: 'gone' })
        else setState({ status: 'error', message: e instanceof ApiError ? e.message : 'The studio did not answer. Try again.' })
      })
    return () => controller.abort()
  }, [token])
  return state
}
