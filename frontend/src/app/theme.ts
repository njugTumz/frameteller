import { useCallback, useEffect, useState } from 'react'

export type ThemeChoice = 'system' | 'light' | 'dark'

const KEY = 'frameteller.theme'
export const THEMES: readonly ThemeChoice[] = ['system', 'light', 'dark']

function stored(): ThemeChoice {
  try {
    const value = window.localStorage.getItem(KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system' // storage can be blocked (private windows); the theme still works for this visit
  }
}

export function applyTheme(choice: ThemeChoice, root: HTMLElement = document.documentElement): void {
  if (choice === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', choice)
}

export function useTheme(): [ThemeChoice, (next: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(stored)
  useEffect(() => applyTheme(choice), [choice])
  const choose = useCallback((next: ThemeChoice) => {
    setChoice(next)
    try {
      if (next === 'system') window.localStorage.removeItem(KEY)
      else window.localStorage.setItem(KEY, next)
    } catch {
      // not remembered, still applied
    }
  }, [])
  return [choice, choose]
}
