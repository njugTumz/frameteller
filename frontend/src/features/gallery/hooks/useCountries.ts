import { useEffect, useState } from 'react'
import type { Countries } from '../../../shared/api/types'
import { listCountries } from '../api'

let loaded: Promise<Countries> | null = null

/** The countries a creator may sign with, loaded once. Empty until then (or if it fails: the field stays optional). */
export function useCountries(): Countries {
  const [countries, setCountries] = useState<Countries>({ codes: [], suggested: null })
  useEffect(() => {
    let live = true
    loaded ??= listCountries()
    loaded
      .then((c) => live && setCountries(c))
      .catch(() => {
        loaded = null
      })
    return () => {
      live = false
    }
  }, [])
  return countries
}
