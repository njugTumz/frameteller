import { useEffect } from 'react'

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

/**
 * Space = "Next shot" while telling. Space would otherwise press whatever button has focus, or scroll,
 * so both keydown and keyup are taken; Enter still presses buttons. Typing in a field is left alone.
 */
export function useBeatShortcut(enabled: boolean, onBeat: () => void): void {
  useEffect(() => {
    if (!enabled) return
    const down = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.altKey || e.ctrlKey || e.metaKey || typing(e.target)) return
      e.preventDefault()
      if (!e.repeat) onBeat()
    }
    const up = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !typing(e.target)) e.preventDefault()
    }
    window.addEventListener('keydown', down, { capture: true })
    window.addEventListener('keyup', up, { capture: true })
    return () => {
      window.removeEventListener('keydown', down, { capture: true })
      window.removeEventListener('keyup', up, { capture: true })
    }
  }, [enabled, onBeat])
}
