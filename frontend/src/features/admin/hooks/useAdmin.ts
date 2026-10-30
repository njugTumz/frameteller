import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import {
  type AdminAction,
  type AdminEntry,
  type Errors,
  type Overview,
  actOn,
  entryVideo,
  getEntries,
  getErrors,
  getOverview,
  removeEntry,
  retryJob,
  setJudgeReserve,
} from '../api'

const KEY = 'frameteller.admin'
const REFRESH_MS = 15_000

/** /admin#<token>: the token is read once, kept for this tab only, and wiped from the address bar. */
function takeToken(): string {
  const fromHash = window.location.hash.slice(1)
  try {
    if (fromHash) sessionStorage.setItem(KEY, fromHash)
    return fromHash || sessionStorage.getItem(KEY) || ''
  } catch {
    return fromHash
  }
}

export function useAdmin() {
  const [token] = useState(takeToken)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [entries, setEntries] = useState<AdminEntry[] | null>(null)
  const [errors, setErrors] = useState<Errors | null>(null)
  const [error, setError] = useState<string | null>(token ? null : 'Open the full admin link.')

  const refresh = useCallback(async () => {
    if (!token) return
    try {
      const [o, e, x] = await Promise.all([getOverview(token), getEntries(token), getErrors(token)])
      setOverview(o)
      setEntries(e)
      setErrors(x)
      setError(null)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'The studio did not answer.')
    }
  }, [token])

  useEffect(() => {
    window.history.replaceState(null, '', '/admin')
    const first = setTimeout(() => void refresh(), 0)
    const timer = setInterval(() => void refresh(), REFRESH_MS)
    return () => {
      clearTimeout(first)
      clearInterval(timer)
    }
  }, [refresh])

  const act = useCallback(
    async (id: string, action: AdminAction | 'remove') => {
      try {
        if (action === 'remove') await removeEntry(token, id)
        else await actOn(token, id, action)
        await refresh()
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'That did not work.')
      }
    },
    [token, refresh],
  )

  const watch = useCallback((id: string) => entryVideo(token, id), [token])

  const lowerReserve = useCallback(
    async (usd: number | null) => {
      try {
        await setJudgeReserve(token, usd)
        await refresh()
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'That did not work.')
      }
    },
    [token, refresh],
  )

  const retry = useCallback(
    async (key: string) => {
      try {
        await retryJob(token, key)
        await refresh()
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'That did not work.')
      }
    },
    [token, refresh],
  )

  return { overview, entries, errors, error, act, watch, lowerReserve, retry }
}
