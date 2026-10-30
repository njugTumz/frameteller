import { useEffect, useState } from 'react'
import type { Presence } from '../machine'
import type { TourStep } from '../steps'

export interface Seen extends Presence {
  /** The element the card points at, where it is now (viewport pixels), if any. */
  rect: DOMRect | null
  /** The open modal dialog, if any: the card renders inside it, or it would be inert behind it. */
  layer: HTMLElement | null
}

const NONE: Seen = { anchor: false, done: false, blocked: false, rect: null, layer: null }

function look(step: TourStep | undefined, target: string | null): Seen {
  if (!step) return NONE
  const find = (selector?: string) => (selector ? document.querySelector<HTMLElement>(selector) : null)
  const pointed = find(target ?? undefined)
  return {
    anchor: !!find(step.anchor),
    done: !!find(step.doneWhen?.selector),
    blocked: !!find(step.blockedBy?.selector),
    rect: pointed ? pointed.getBoundingClientRect() : null,
    layer: document.querySelector<HTMLDialogElement>('dialog[open]'),
  }
}

const same = (a: Seen, b: Seen) =>
  a.anchor === b.anchor &&
  a.done === b.done &&
  a.blocked === b.blocked &&
  a.layer === b.layer &&
  a.rect?.top === b.rect?.top &&
  a.rect?.left === b.rect?.left &&
  a.rect?.width === b.rect?.width &&
  a.rect?.height === b.rect?.height

/** Watches the page for the step's elements: the studio adds them as session events arrive. */
export function usePresence(step: TourStep | undefined, target: (seen: Presence) => string | null): Seen {
  const [seen, setSeen] = useState<Seen>(NONE)
  useEffect(() => {
    let frame = 0
    const update = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const presence = look(step, null)
        const next = look(step, target(presence))
        setSeen((prev) => (same(prev, next) ? prev : next))
      })
    }
    update()
    const observer = new MutationObserver(update)
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-status', 'data-phase', 'data-selected', 'open'] })
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [step, target])
  return seen
}
