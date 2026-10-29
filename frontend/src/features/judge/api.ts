import { api, call } from '../../shared/api/client'

/** Trade the judge link's token (from the URL fragment) for the signed judge cookie. */
export function enterJudge(token: string) {
  return call(() => api.POST('/judge', { body: { token } }))
}

export function leaveJudge() {
  return call(() => api.DELETE('/judge'))
}
