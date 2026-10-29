import { useEffect, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import { checkStudioStatus } from '../../../shared/status/api'
import { enterJudge } from '../api'

export type JudgeLinkState = { kind: 'checking' } | { kind: 'ok'; until: string | null } | { kind: 'failed'; message: string }

const INCOMPLETE = 'This judge link is incomplete. Open the full link you were sent.'

/**
 * /judge#<token>: send the token once, then wipe it from the address bar and history, so it is never
 * bookmarked, shared or sent anywhere else. The cookie the backend sets is what lets the judge in.
 */
export function useJudgeLink(): JudgeLinkState {
  const [token] = useState(() => window.location.hash.slice(1)) // read once: StrictMode runs effects twice
  const [state, setState] = useState<JudgeLinkState>(() => (token ? { kind: 'checking' } : { kind: 'failed', message: INCOMPLETE }))
  useEffect(() => {
    window.history.replaceState(null, '', '/judge')
    if (!token) return
    let live = true
    enterJudge(token)
      .then((pass) => {
        if (!live) return
        setState({ kind: 'ok', until: pass.until ?? null })
        void checkStudioStatus()
      })
      .catch((e: unknown) => {
        if (live) setState({ kind: 'failed', message: e instanceof ApiError ? e.message : 'The studio did not answer. Try the link again.' })
      })
    return () => {
      live = false
    }
  }, [token])
  return state
}
