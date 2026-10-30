import { useCallback, useState } from 'react'
import { ApiError } from '../../../shared/api/client'
import { reportProblem } from '../api'
import { MAX_REPORT } from '../limits'

export type ReportState = 'idle' | 'sending' | 'sent'

/** Send one report for this project; the studio limits how many a visitor sends a day. */
export function useReportProblem(projectId: string) {
  const [state, setState] = useState<ReportState>('idle')
  const [error, setError] = useState<string | null>(null)

  const send = useCallback(
    async (text: string) => {
      setError(null)
      setState('sending')
      try {
        await reportProblem(projectId, text.trim().slice(0, MAX_REPORT))
        setState('sent')
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'The studio did not answer. Try again.')
        setState('idle')
      }
    },
    [projectId],
  )

  const reset = useCallback(() => {
    setError(null)
    setState('idle')
  }, [])

  return { state, error, send, reset }
}
