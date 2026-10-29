import { api, call } from '../api/client'
import { useStudioStatus } from './store'

/** Ask the backend whether the studio is paused or full, and remember it. A failure changes nothing. */
export async function checkStudioStatus(): Promise<void> {
  try {
    const status = await call(() => api.GET('/status'))
    useStudioStatus.getState().set({ paused: status.paused, full: status.full })
  } catch {
    // unreachable or asleep: the wake notice covers it
  }
}
